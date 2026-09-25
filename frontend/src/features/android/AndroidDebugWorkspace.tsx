import {
  Button,
  ButtonGroup,
  Callout,
  Card,
  Divider,
  Elevation,
  HTMLSelect,
  Spinner,
  Tag,
} from '@blueprintjs/core'
import type { PointerEvent as ReactPointerEvent } from 'react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type {
  AndroidDebugState,
  AndroidDeviceSummary,
  AndroidPointerPoint,
  AndroidUiBounds,
  AndroidUiNode,
} from '../../types/android-debug'
import type { VisionDetection } from '../../types/vision'
import { androidApi } from './android-api'
import { appendSampledPoint, isTapPath, mapPointerToFrame } from './pointer-gesture'
import {
  buildCompressedHierarchy,
  countCompressedRows,
  isActionableUiNode,
  isMeaningfulUiNode,
} from './ui-tree/hierarchy-compression'
import type { CompressedHierarchyRow } from './ui-tree/hierarchy-compression'
import type { AndroidDebugController } from './useAndroidDebug'

interface AndroidDebugWorkspaceProps {
  controller: AndroidDebugController
  devices: AndroidDeviceSummary[]
  onDeviceChange: (deviceId: string) => void
}

interface AndroidOverlayProps {
  width: number
  height: number
  detections: VisionDetection[]
  selectedId: string | null
  highlightedId: string | null
  plannedPoint: { x: number; y: number } | null
  uiBounds: AndroidUiBounds | null
  uiLabel: string | null
  pointerPath: AndroidPointerPoint[]
}

interface StableGeometry {
  width: number
  height: number
}

interface PointerBoundsSnapshot {
  left: number
  top: number
  width: number
  height: number
}

const DEFAULT_PHONE_GEOMETRY: StableGeometry = { width: 1080, height: 2280 }

function validGeometry(
  width: number | null | undefined,
  height: number | null | undefined,
): StableGeometry | null {
  return typeof width === 'number' &&
    Number.isFinite(width) &&
    width > 0 &&
    typeof height === 'number' &&
    Number.isFinite(height) &&
    height > 0
    ? { width, height }
    : null
}

function AndroidOverlay({
  width,
  height,
  detections,
  selectedId,
  highlightedId,
  plannedPoint,
  uiBounds,
  uiLabel,
  pointerPath,
}: AndroidOverlayProps) {
  const scale = Math.max(width, height) / 900
  const pointerStart = pointerPath[0]
  const pointerEnd = pointerPath.at(-1)
  return (
    <svg
      className="android-screen-overlay"
      viewBox={`0 0 ${width.toString()} ${height.toString()}`}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    >
      {detections.map((detection) => (
        <g
          key={detection.id}
          className={[
            'android-detection-box',
            detection.id === selectedId ? 'is-selected' : '',
            detection.id === highlightedId ? 'is-highlighted' : '',
          ]
            .filter(Boolean)
            .join(' ')}
        >
          <rect
            x={detection.bbox.x}
            y={detection.bbox.y}
            width={detection.bbox.width}
            height={detection.bbox.height}
            vectorEffect="non-scaling-stroke"
          />
          <text
            x={detection.bbox.x}
            y={Math.max(detection.bbox.y - 6 * scale, 13 * scale)}
          >
            {detection.label} · {(detection.confidence * 100).toFixed(1)}%
          </text>
        </g>
      ))}
      {uiBounds && (
        <g className="android-ui-node-box">
          <rect
            x={uiBounds.left}
            y={uiBounds.top}
            width={uiBounds.right - uiBounds.left}
            height={uiBounds.bottom - uiBounds.top}
            vectorEffect="non-scaling-stroke"
          />
          {uiLabel && (
            <text x={uiBounds.left} y={Math.max(uiBounds.top - 6 * scale, 13 * scale)}>
              {uiLabel}
            </text>
          )}
          <circle
            cx={(uiBounds.left + uiBounds.right) / 2}
            cy={(uiBounds.top + uiBounds.bottom) / 2}
            r={Math.max(5 * scale, 3)}
            vectorEffect="non-scaling-stroke"
          />
        </g>
      )}
      {plannedPoint && (
        <g className="android-planned-tap">
          <circle
            cx={plannedPoint.x}
            cy={plannedPoint.y}
            r={Math.max(10 * scale, 5)}
            vectorEffect="non-scaling-stroke"
          />
          <path
            d={`M ${plannedPoint.x - 16 * scale} ${plannedPoint.y} H ${plannedPoint.x + 16 * scale} M ${plannedPoint.x} ${plannedPoint.y - 16 * scale} V ${plannedPoint.y + 16 * scale}`}
            vectorEffect="non-scaling-stroke"
          />
        </g>
      )}
      {pointerStart && pointerEnd && (
        <g className="android-pointer-path">
          {pointerPath.length > 1 && (
            <polyline
              points={pointerPath.map((point) => `${point.x},${point.y}`).join(' ')}
              vectorEffect="non-scaling-stroke"
            />
          )}
          <circle
            className="android-pointer-path__start"
            cx={pointerStart.x}
            cy={pointerStart.y}
            r={Math.max(7 * scale, 4)}
            vectorEffect="non-scaling-stroke"
          />
          <circle
            className="android-pointer-path__current"
            cx={pointerEnd.x}
            cy={pointerEnd.y}
            r={Math.max(9 * scale, 5)}
            vectorEffect="non-scaling-stroke"
          />
        </g>
      )}
    </svg>
  )
}

function pretty(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'string') return value
  return JSON.stringify(value)
}

function macroIntent(status: string | undefined) {
  if (status === 'RUNNING' || status === 'STEPPING') return 'success' as const
  if (status === 'PAUSED') return 'warning' as const
  return 'none' as const
}

export function AndroidDebugWorkspace({
  controller,
  devices,
  onDeviceChange,
}: AndroidDebugWorkspaceProps) {
  const { status, debug } = controller
  const currentGeometry = useMemo(
    () =>
      validGeometry(status?.stream?.width, status?.stream?.height) ??
      validGeometry(status?.agent?.device.width, status?.agent?.device.height) ??
      validGeometry(debug?.frame?.width, debug?.frame?.height),
    [debug?.frame, status?.agent?.device, status?.stream],
  )
  const [stableGeometry, setStableGeometry] = useState<StableGeometry>(
    () => currentGeometry ?? DEFAULT_PHONE_GEOMETRY,
  )
  const frameWidth = stableGeometry.width
  const frameHeight = stableGeometry.height
  const canControl = Boolean(
    status?.connected &&
    status.agent?.accessibility_enabled &&
    status.agent.remote_control_enabled,
  )
  const useStream = Boolean(status?.stream?.running && !controller.streamFailed)
  const imageSource = useStream
    ? androidApi.streamUrl(controller.deviceId ?? '', controller.streamNonce)
    : androidApi.screenshotUrl(
        controller.deviceId ?? '',
        debug?.frame?.frame_id ?? controller.streamNonce,
      )
  const plannedPoint = debug?.decision.target?.screen ?? null
  const selected = useMemo(
    () =>
      debug?.detections.find(
        (detection) => detection.id === controller.selectedDetectionId,
      ) ?? null,
    [controller.selectedDetectionId, debug?.detections],
  )
  const selectedUiNode = useMemo(
    () =>
      controller.uiTree?.nodes.find(
        (node) => node.node_id === controller.selectedUiNodeId,
      ) ?? null,
    [controller.selectedUiNodeId, controller.uiTree?.nodes],
  )
  const [hoveredUiNodeId, setHoveredUiNodeId] = useState<string | null>(null)
  const hoveredUiNode = useMemo(
    () =>
      controller.uiTree?.nodes.find((node) => node.node_id === hoveredUiNodeId) ?? null,
    [controller.uiTree?.nodes, hoveredUiNodeId],
  )
  const overlayUiNode = hoveredUiNode ?? selectedUiNode
  const selectedUiBounds =
    controller.uiTree?.screen_width === frameWidth &&
    controller.uiTree.screen_height === frameHeight
      ? (overlayUiNode?.bounds ?? null)
      : null
  const selectedUiLabel = overlayUiNode
    ? (overlayUiNode.text ??
      overlayUiNode.content_description ??
      shortClassName(overlayUiNode.class_name))
    : null
  const overlayFrameMatches =
    !debug?.frame ||
    (debug.frame.width === frameWidth && debug.frame.height === frameHeight)
  const [recordingPath, setRecordingPath] = useState<AndroidPointerPoint[]>([])
  const [recentPath, setRecentPath] = useState<AndroidPointerPoint[]>([])
  const isRecording = recordingPath.length > 0
  const activePointer = useRef<{
    id: number
    startedAt: number
    points: AndroidPointerPoint[]
    bounds: PointerBoundsSnapshot
    frameWidth: number
    frameHeight: number
  } | null>(null)
  const recentPathTimer = useRef<number | null>(null)

  const cancelPointerRecording = useCallback(() => {
    activePointer.current = null
    setRecordingPath([])
  }, [])

  useEffect(() => {
    activePointer.current = null
    const reset = window.setTimeout(() => {
      setRecordingPath([])
      setRecentPath([])
      setHoveredUiNodeId(null)
    }, 0)
    return () => window.clearTimeout(reset)
  }, [controller.deviceId])

  useEffect(() => {
    if (!currentGeometry || isRecording) return undefined
    const update = window.setTimeout(() => {
      if (activePointer.current) return
      setStableGeometry((previous) =>
        previous.width === currentGeometry.width &&
        previous.height === currentGeometry.height
          ? previous
          : currentGeometry,
      )
    }, 0)
    return () => window.clearTimeout(update)
  }, [currentGeometry, isRecording])

  useEffect(() => {
    if (!controller.manualTapEnabled || !status?.connected || controller.streamFailed) {
      activePointer.current = null
      const reset = window.setTimeout(() => setRecordingPath([]), 0)
      return () => window.clearTimeout(reset)
    }
    return undefined
  }, [controller.manualTapEnabled, controller.streamFailed, status?.connected])

  useEffect(
    () => () => {
      if (recentPathTimer.current !== null) {
        window.clearTimeout(recentPathTimer.current)
      }
    },
    [],
  )

  const eventPoint = (
    event: ReactPointerEvent<HTMLDivElement>,
    bounds: PointerBoundsSnapshot,
    width: number,
    height: number,
  ): { x: number; y: number } | null =>
    mapPointerToFrame(event.clientX, event.clientY, bounds, width, height)

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!controller.manualTapEnabled || !canControl || event.button !== 0) return
    const rect = event.currentTarget.getBoundingClientRect()
    const bounds = {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
    }
    const point = eventPoint(event, bounds, frameWidth, frameHeight)
    if (!point) return
    event.preventDefault()
    event.currentTarget.setPointerCapture?.(event.pointerId)
    const first = { ...point, t_ms: 0 }
    activePointer.current = {
      id: event.pointerId,
      startedAt: performance.now(),
      points: [first],
      bounds,
      frameWidth,
      frameHeight,
    }
    setRecordingPath([first])
  }

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const active = activePointer.current
    if (!active || active.id !== event.pointerId) return
    const point = eventPoint(
      event,
      active.bounds,
      active.frameWidth,
      active.frameHeight,
    )
    if (!point) return
    event.preventDefault()
    const sampled = appendSampledPoint(active.points, {
      ...point,
      t_ms: Math.max(0, Math.round(performance.now() - active.startedAt)),
    })
    if (sampled !== active.points) {
      active.points = sampled
      setRecordingPath(sampled)
    }
  }

  const handlePointerUp = (event: ReactPointerEvent<HTMLDivElement>) => {
    const active = activePointer.current
    if (!active || active.id !== event.pointerId) return
    event.preventDefault()
    const fallback = active.points.at(-1)
    if (!fallback) {
      cancelPointerRecording()
      return
    }
    const mapped =
      eventPoint(event, active.bounds, active.frameWidth, active.frameHeight) ??
      fallback
    const elapsed = Math.max(1, Math.round(performance.now() - active.startedAt))
    const completed = appendSampledPoint(
      active.points,
      { x: mapped.x, y: mapped.y, t_ms: elapsed },
      { force: true },
    )
    activePointer.current = null
    setRecordingPath([])
    setRecentPath(completed)
    if (recentPathTimer.current !== null) window.clearTimeout(recentPathTimer.current)
    recentPathTimer.current = window.setTimeout(() => setRecentPath([]), 900)
    const first = completed[0]
    if (!first) return
    if (isTapPath(completed)) {
      void controller.tap(first.x, first.y)
    } else {
      void controller.gesture(completed)
    }
  }

  const handlePointerCancel = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (activePointer.current?.id !== event.pointerId) return
    event.preventDefault()
    cancelPointerRecording()
  }

  return (
    <section className="android-debug-workspace" aria-labelledby="android-debug-title">
      <div className="android-debug-heading">
        <div>
          <span>PC-controlled canonical screen</span>
          <h1 id="android-debug-title">Android Remote Debug</h1>
        </div>
        <label className="android-device-select">
          <span>Android Device</span>
          <HTMLSelect
            aria-label="Android Device"
            value={controller.deviceId ?? ''}
            disabled={devices.length === 0}
            onChange={(event) => onDeviceChange(event.currentTarget.value)}
          >
            {devices.length === 0 && <option value="">No devices configured</option>}
            {devices.map((device) => (
              <option key={device.id} value={device.id}>
                {device.name} · {device.connected ? 'ONLINE' : 'OFFLINE'} ·{' '}
                {device.stream_running ? 'LIVE' : 'OFF'} · {device.macro_status}
              </option>
            ))}
          </HTMLSelect>
        </label>
        <div className="android-debug-heading__tags">
          <Tag intent={status?.connected ? 'success' : 'danger'} minimal>
            Android {status?.connected ? 'ONLINE' : 'OFFLINE'}
          </Tag>
          <Tag intent={status?.stream?.running ? 'success' : 'warning'} minimal>
            Stream {status?.stream?.running ? 'LIVE' : 'FALLBACK'}
          </Tag>
          <Tag intent={controller.uiTree ? 'success' : 'none'} minimal>
            UI Tree {controller.uiTree ? 'OK' : '—'}
          </Tag>
          <Tag intent={macroIntent(debug?.macro.status)} minimal>
            Macro {debug?.macro.status ?? 'IDLE'}
          </Tag>
        </div>
      </div>

      <div className="android-debug-grid">
        <Card
          className="android-live-card"
          elevation={Elevation.ONE}
          data-editor-pane="live"
        >
          <header className="android-card-heading">
            <div>
              <span>Canonical source</span>
              <strong>Android Live Screen</strong>
            </div>
            <div>
              {frameWidth > 0 && frameHeight > 0 && (
                <Tag minimal>
                  {frameWidth} × {frameHeight}
                </Tag>
              )}
              <Tag minimal>{status?.stream?.fps?.toFixed(1) ?? '—'} FPS</Tag>
              <Tag minimal>{status?.stream?.frame_age_ms?.toFixed(0) ?? '—'} ms</Tag>
            </div>
          </header>

          <div className="android-live-shell">
            <div
              className={`android-live-stage ${controller.manualTapEnabled ? 'is-tap-mode' : ''}`}
              style={{
                aspectRatio: `${frameWidth.toString()} / ${frameHeight.toString()}`,
              }}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerCancel}
              onContextMenu={(event) => event.preventDefault()}
              role={controller.manualTapEnabled ? 'button' : undefined}
              tabIndex={controller.manualTapEnabled ? 0 : undefined}
              data-geometry={`${frameWidth.toString()}x${frameHeight.toString()}`}
            >
              <img
                src={status?.connected ? imageSource : undefined}
                alt="Android live screen"
                draggable={false}
                onError={() => {
                  if (useStream) controller.setStreamFailed(true)
                }}
              />
              <AndroidOverlay
                width={frameWidth}
                height={frameHeight}
                detections={overlayFrameMatches ? (debug?.detections ?? []) : []}
                selectedId={controller.selectedDetectionId}
                highlightedId={controller.highlightedDetectionId}
                plannedPoint={overlayFrameMatches ? plannedPoint : null}
                uiBounds={selectedUiBounds}
                uiLabel={selectedUiLabel}
                pointerPath={recordingPath.length > 0 ? recordingPath : recentPath}
              />
              <div className="android-live-badges">
                <Tag intent={useStream ? 'success' : 'warning'} minimal>
                  {useStream ? 'MJPEG LIVE' : 'SCREENSHOT FALLBACK'}
                </Tag>
                <Tag
                  className={controller.manualTapEnabled ? '' : 'is-placeholder-badge'}
                  intent="warning"
                >
                  MANUAL CONTROL ACTIVE
                </Tag>
                {!overlayFrameMatches && (
                  <Tag intent="warning">OVERLAY GEOMETRY STALE</Tag>
                )}
              </div>
              <div
                className={`android-screen-empty ${status?.connected ? 'is-hidden' : ''}`}
                aria-hidden={status?.connected}
              >
                {status === null ? <Spinner size={36} /> : null}
                <strong>
                  {status === null ? 'Connecting' : 'Android unavailable'}
                </strong>
                <span>{status?.error ?? 'Waiting for Android Agent status.'}</span>
              </div>
            </div>
          </div>

          <div className="android-control-bar">
            <Button
              active={controller.manualTapEnabled}
              intent={controller.manualTapEnabled ? 'warning' : 'none'}
              icon="hand"
              text={
                controller.manualTapEnabled ? 'Manual Control On' : 'Manual Control'
              }
              disabled={!canControl}
              onClick={() =>
                controller.setManualTapEnabled(!controller.manualTapEnabled)
              }
            />
            <Button
              icon="camera"
              text="Screenshot"
              loading={controller.busy === 'Screenshot'}
              disabled={!status?.connected}
              onClick={() => void controller.saveScreenshot()}
            />
            <Button
              icon="undo"
              text="Back"
              loading={controller.busy === 'Back'}
              disabled={!canControl}
              onClick={() => void controller.back()}
            />
            <Button
              icon="home"
              text="Home"
              loading={controller.busy === 'Home'}
              disabled={!canControl}
              onClick={() => void controller.home()}
            />
            <Button
              className={controller.streamFailed ? '' : 'is-placeholder-control'}
              icon="refresh"
              text="Reconnect Stream"
              disabled={!controller.streamFailed}
              onClick={controller.reconnectStream}
            />
            <Divider />
            <ButtonGroup>
              <Button
                icon="play"
                text="Start"
                onClick={() => void controller.macroStart()}
                disabled={!status?.connected}
              />
              <Button
                icon="step-forward"
                text="Step"
                intent="primary"
                loading={controller.busy === 'Macro step'}
                onClick={() => void controller.macroStep()}
                disabled={!canControl}
              />
              <Button
                icon="pause"
                text="Pause"
                onClick={() => void controller.macroPause()}
                disabled={!status?.connected}
              />
              <Button
                icon="stop"
                text="Stop"
                onClick={() => void controller.macroStop()}
                disabled={!status?.connected}
              />
              <Button
                icon="reset"
                text="Reset"
                onClick={() => void controller.macroReset()}
                disabled={!status?.configured}
              />
            </ButtonGroup>
          </div>
        </Card>

        <Card
          className="android-hierarchy-pane"
          elevation={Elevation.ONE}
          data-editor-pane="hierarchy"
        >
          <UiTreeHierarchy
            key={controller.deviceId ?? 'no-device'}
            controller={controller}
            onHoverNode={setHoveredUiNodeId}
          />
        </Card>

        <Card
          className="android-node-inspector-pane"
          elevation={Elevation.ONE}
          data-editor-pane="inspector"
        >
          <UiNodeInspector
            controller={controller}
            node={selectedUiNode}
            frameWidth={frameWidth}
            frameHeight={frameHeight}
          />
          <InspectorMessages controller={controller} />
        </Card>
      </div>

      <AndroidConsolePanel controller={controller} selectedDetection={selected} />
    </section>
  )
}

type ConsoleTab = 'console' | 'vision' | 'macro'

function shortClassName(className: string | null): string {
  return className?.split('.').at(-1) ?? 'Node'
}

function nodeTitle(node: AndroidUiNode): string {
  return node.text ?? node.content_description ?? shortClassName(node.class_name)
}

function nodeFingerprint(node: AndroidUiNode): string {
  return JSON.stringify([
    node.view_id_resource_name,
    node.content_description,
    node.text,
    node.class_name,
    node.depth,
  ])
}

function hierarchyRoot(root: AndroidUiNode, nodes: AndroidUiNode[]): AndroidUiNode {
  if (root.children?.length || nodes.length <= 1) return root
  const copies = new Map(
    nodes.map((node) => [node.node_id, { ...node, children: [] as AndroidUiNode[] }]),
  )
  for (const node of copies.values()) {
    if (node.parent_id) copies.get(node.parent_id)?.children?.push(node)
  }
  return copies.get(root.node_id) ?? root
}

function nodeMatches(node: AndroidUiNode, query: string): boolean {
  if (!query) return true
  return [
    node.text,
    node.content_description,
    node.view_id_resource_name,
    node.class_name,
    node.node_id,
  ].some((value) => value?.toLocaleLowerCase().includes(query))
}

function collectMatchingBranches(
  node: AndroidUiNode,
  predicate: (node: AndroidUiNode) => boolean,
  matches: Set<string>,
): boolean {
  let included = predicate(node)
  for (const child of node.children ?? []) {
    if (collectMatchingBranches(child, predicate, matches)) included = true
  }
  if (included) matches.add(node.node_id)
  return included
}

function preferredSelector(node: AndroidUiNode): string {
  if (node.view_id_resource_name)
    return `viewId == ${JSON.stringify(node.view_id_resource_name)}`
  if (node.content_description)
    return `contentDescription == ${JSON.stringify(node.content_description)}`
  if (node.text)
    return `text == ${JSON.stringify(node.text)}${node.clickable ? ' && clickable == true' : ''}`
  if (node.class_name) return `className == ${JSON.stringify(node.class_name)}`
  return `snapshotNode == ${JSON.stringify(node.node_id)}`
}

function InspectorMessages({ controller }: { controller: AndroidDebugController }) {
  const { status } = controller
  return (
    <div className="android-debug-message-slot" aria-live="polite">
      {status && !status.configured && (
        <Callout intent="warning" title="Android Agent is not configured">
          Configure an Android Agent in the PC backend.
        </Callout>
      )}
      {controller.error && (
        <Callout intent="danger" title="Android debug error">
          {controller.error}
        </Callout>
      )}
      {controller.notice && <Callout intent="success">{controller.notice}</Callout>}
      {(!status || status.configured) && !controller.error && !controller.notice && (
        <span className="android-message-placeholder" aria-hidden="true">
          No active messages.
        </span>
      )}
    </div>
  )
}

function UiTreeHierarchy({
  controller,
  onHoverNode,
}: {
  controller: AndroidDebugController
  onHoverNode: (nodeId: string | null) => void
}) {
  const [query, setQuery] = useState('')
  const [visibleOnly, setVisibleOnly] = useState(true)
  const [clickableOnly, setClickableOnly] = useState(false)
  const [enabledOnly, setEnabledOnly] = useState(false)
  const [compressChains, setCompressChains] = useState(true)
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set())
  const normalized = query.trim().toLocaleLowerCase()
  const tree = useMemo(
    () =>
      controller.uiTree
        ? hierarchyRoot(controller.uiTree.root, controller.uiTree.nodes)
        : null,
    [controller.uiTree],
  )

  const isResult = (node: AndroidUiNode) =>
    (!visibleOnly || node.visible_to_user) &&
    (!clickableOnly || node.clickable) &&
    (!enabledOnly || node.enabled) &&
    nodeMatches(node, normalized)
  const hierarchy = useMemo(() => {
    if (!tree) return null
    const visibleBranchIds = new Set<string>()
    const selectedBranchIds = new Set<string>()
    const result = (node: AndroidUiNode) =>
      (!visibleOnly || node.visible_to_user) &&
      (!clickableOnly || node.clickable) &&
      (!enabledOnly || node.enabled) &&
      nodeMatches(node, normalized)
    collectMatchingBranches(tree, result, visibleBranchIds)
    collectMatchingBranches(
      tree,
      (candidate) => candidate.node_id === controller.selectedUiNodeId,
      selectedBranchIds,
    )
    if (!visibleBranchIds.has(tree.node_id)) {
      return { root: null, selectedBranchIds, rowCount: 0 }
    }
    const root = buildCompressedHierarchy(tree, {
      compress: compressChains,
      includeNode: (node) => visibleBranchIds.has(node.node_id),
    })
    return { root, selectedBranchIds, rowCount: countCompressedRows(root) }
  }, [
    clickableOnly,
    compressChains,
    controller.selectedUiNodeId,
    enabledOnly,
    normalized,
    tree,
    visibleOnly,
  ])

  const toggleExpanded = (row: CompressedHierarchyRow) => {
    const terminal = row.chain.at(-1)
    if (!terminal) return
    const key = nodeFingerprint(terminal)
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <section className="android-hierarchy-panel" aria-label="UI Tree Hierarchy">
      <header className="android-editor-section-heading">
        <div>
          <strong>UI Tree Hierarchy</strong>
          <small>
            {tree?.package_name ?? controller.uiTree?.package_name ?? 'No package'}
          </small>
        </div>
        <Button
          minimal
          small
          icon="refresh"
          aria-label="Refresh UI tree"
          loading={controller.uiTreeLoading}
          disabled={!controller.deviceId}
          onClick={() => void controller.refreshUiTree()}
        />
      </header>
      <div className="android-tree-status">
        <span>{controller.uiTree?.node_count ?? 0} nodes</span>
        {hierarchy?.root && <span>· {hierarchy.rowCount} rows</span>}
        <span>
          {controller.uiTree?.captured_at
            ? new Date(controller.uiTree.captured_at).toLocaleTimeString()
            : 'not captured'}
        </span>
        {controller.uiTree?.truncated && (
          <Tag intent="warning" minimal>
            TRUNCATED
          </Tag>
        )}
      </div>
      <input
        className="android-tree-search"
        aria-label="Search UI tree"
        value={query}
        placeholder="Search text, class, view id…"
        onChange={(event) => setQuery(event.currentTarget.value)}
      />
      <div className="android-tree-filters">
        <label>
          <input
            type="checkbox"
            checked={visibleOnly}
            onChange={(event) => setVisibleOnly(event.currentTarget.checked)}
          />
          Visible
        </label>
        <label>
          <input
            type="checkbox"
            checked={clickableOnly}
            onChange={(event) => setClickableOnly(event.currentTarget.checked)}
          />
          Clickable
        </label>
        <label>
          <input
            type="checkbox"
            checked={enabledOnly}
            onChange={(event) => setEnabledOnly(event.currentTarget.checked)}
          />
          Enabled
        </label>
        <label className="android-tree-compression-toggle">
          <input
            type="checkbox"
            checked={compressChains}
            onChange={(event) => setCompressChains(event.currentTarget.checked)}
          />
          Compress chains
        </label>
      </div>
      <div className="android-hierarchy-scroll">
        {controller.uiTreeLoading && !tree && (
          <div className="android-panel-empty">Loading UI tree…</div>
        )}
        {controller.uiTreeError && (
          <Callout intent="warning" title="UI tree unavailable">
            {controller.uiTreeError}
          </Callout>
        )}
        {hierarchy?.root && (
          <CompressedHierarchyRowView
            row={hierarchy.root}
            depth={0}
            expanded={expanded}
            searchActive={Boolean(normalized)}
            isResult={isResult}
            selectedBranchIds={hierarchy.selectedBranchIds}
            selectedNodeId={controller.selectedUiNodeId}
            onToggle={toggleExpanded}
            onSelect={controller.setSelectedUiNodeId}
            onHover={onHoverNode}
          />
        )}
        {!controller.uiTreeLoading && !controller.uiTreeError && !tree && (
          <div className="android-panel-empty">No UI tree snapshot.</div>
        )}
        {tree && !hierarchy?.root && (
          <div className="android-panel-empty">No matching UI nodes.</div>
        )}
      </div>
    </section>
  )
}

function CompressedHierarchyRowView({
  row,
  depth,
  expanded,
  searchActive,
  isResult,
  selectedBranchIds,
  selectedNodeId,
  onToggle,
  onSelect,
  onHover,
}: {
  row: CompressedHierarchyRow
  depth: number
  expanded: Set<string>
  searchActive: boolean
  isResult: (node: AndroidUiNode) => boolean
  selectedBranchIds: Set<string>
  selectedNodeId: string | null
  onToggle: (row: CompressedHierarchyRow) => void
  onSelect: (nodeId: string | null) => void
  onHover: (nodeId: string | null) => void
}) {
  const terminal = row.chain.at(-1)
  if (!terminal) return null
  const key = nodeFingerprint(terminal)
  const open =
    searchActive ||
    selectedBranchIds.has(row.terminalNodeId) ||
    (depth === 0 ? !expanded.has(key) : expanded.has(key))
  const rowLabel = row.chain.map((node) => nodeTitle(node)).join(' / ')
  return (
    <div className="android-hierarchy-branch">
      <div
        className="android-hierarchy-row android-compressed-hierarchy-row"
        style={{ paddingLeft: `${(depth * 14).toString()}px` }}
      >
        <button
          className="android-tree-chevron"
          type="button"
          aria-label={`${open ? 'Collapse' : 'Expand'} ${rowLabel}`}
          disabled={row.children.length === 0}
          onClick={() => onToggle(row)}
        >
          {row.children.length ? (open ? '▾' : '▸') : '·'}
        </button>
        <div className="android-tree-chain" aria-label={rowLabel}>
          {row.chain.map((node, index) => {
            const content = node.text?.trim() || node.content_description?.trim()
            const selected = node.node_id === selectedNodeId
            const actionable = isActionableUiNode(node)
            const meaningful = isMeaningfulUiNode(node)
            return (
              <span key={node.node_id} className="android-tree-chain-item">
                {index > 0 && (
                  <span className="android-tree-chain-separator" aria-hidden="true">
                    /
                  </span>
                )}
                <button
                  className={[
                    'android-tree-segment',
                    selected ? 'is-selected' : '',
                    searchActive && isResult(node) ? 'is-search-match' : '',
                    actionable ? 'is-actionable' : '',
                    !actionable && !meaningful ? 'is-wrapper' : '',
                    !node.visible_to_user || !node.enabled ? 'is-muted' : '',
                  ]
                    .filter(Boolean)
                    .join(' ')}
                  type="button"
                  title={`${node.class_name ?? 'Unknown class'}\nnode_id=${node.node_id}\nbounds=[${node.bounds.left}, ${node.bounds.top}, ${node.bounds.right}, ${node.bounds.bottom}]`}
                  onClick={() => onSelect(node.node_id)}
                  onMouseEnter={() => onHover(node.node_id)}
                  onMouseLeave={() => onHover(null)}
                >
                  <span>{shortClassName(node.class_name)}</span>
                  {content && (
                    <span className="android-tree-segment-preview">
                      “{content.length > 32 ? `${content.slice(0, 32)}…` : content}”
                    </span>
                  )}
                </button>
              </span>
            )
          })}
        </div>
        {row.children.length > 0 && (
          <span className="android-tree-child-count">{row.children.length}</span>
        )}
      </div>
      {open &&
        row.children.map((child) => (
          <CompressedHierarchyRowView
            key={child.id}
            row={child}
            depth={depth + 1}
            expanded={expanded}
            searchActive={searchActive}
            isResult={isResult}
            selectedBranchIds={selectedBranchIds}
            selectedNodeId={selectedNodeId}
            onToggle={onToggle}
            onSelect={onSelect}
            onHover={onHover}
          />
        ))}
    </div>
  )
}

function UiNodeInspector({
  controller,
  node,
  frameWidth,
  frameHeight,
}: {
  controller: AndroidDebugController
  node: AndroidUiNode | null
  frameWidth: number
  frameHeight: number
}) {
  if (!node) {
    return (
      <section className="android-node-inspector" aria-label="Node Inspector">
        <header className="android-editor-section-heading">
          <strong>Node Inspector</strong>
        </header>
        <div className="android-panel-empty">Select a UI node to inspect it.</div>
      </section>
    )
  }
  const { bounds } = node
  const width = bounds.right - bounds.left
  const height = bounds.bottom - bounds.top
  const geometryMatches =
    controller.uiTree?.screen_width === frameWidth &&
    controller.uiTree.screen_height === frameHeight
  const inViewport =
    geometryMatches &&
    width > 0 &&
    height > 0 &&
    bounds.left >= 0 &&
    bounds.top >= 0 &&
    bounds.right <= frameWidth &&
    bounds.bottom <= frameHeight
  const canTap = node.visible_to_user && node.enabled && inViewport
  const centerX = (bounds.left + bounds.right) / 2
  const centerY = (bounds.top + bounds.bottom) / 2
  const fields = [
    ['Node ID', node.node_id],
    ['Parent', node.parent_id ?? '—'],
    ['Depth', node.depth.toString()],
    ['Class', node.class_name ?? '—'],
    ['Package', node.package_name ?? '—'],
    ['Text', node.text ?? '—'],
    ['Description', node.content_description ?? '—'],
    ['View ID', node.view_id_resource_name ?? '—'],
    ['Bounds', `${bounds.left}, ${bounds.top} → ${bounds.right}, ${bounds.bottom}`],
    ['Size', `${width} × ${height}`],
    ['Center', `${centerX.toFixed(1)}, ${centerY.toFixed(1)}`],
  ]
  const states = [
    ['clickable', node.clickable],
    ['enabled', node.enabled],
    ['focusable', node.focusable],
    ['focused', node.focused],
    ['selected', node.selected],
    ['checked', node.checked],
    ['checkable', node.checkable],
    ['scrollable', node.scrollable],
    ['editable', node.editable],
    ['visible', node.visible_to_user],
    ['password', node.password],
  ] as const
  return (
    <section className="android-node-inspector" aria-label="Node Inspector">
      <header className="android-editor-section-heading">
        <div>
          <strong>Node Inspector</strong>
          <small>{nodeTitle(node)}</small>
        </div>
        {!inViewport && <Tag intent="warning">OFFSCREEN</Tag>}
      </header>
      <div className="android-node-inspector-scroll">
        <dl className="android-node-fields">
          {fields.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd title={value}>{value}</dd>
            </div>
          ))}
        </dl>
        <div className="android-node-state-flags">
          {states.map(([label, active]) => (
            <span key={label} className={active ? 'is-active' : ''}>
              {label}
            </span>
          ))}
        </div>
        <label className="android-selector-preview">
          <span>Preferred selector</span>
          <textarea readOnly rows={2} value={preferredSelector(node)} />
        </label>
        <div className="android-node-actions">
          <Button
            small
            intent="primary"
            icon="locate"
            text="Tap Center"
            disabled={!canTap}
            onClick={() => void controller.tap(centerX, centerY)}
          />
          {!canTap && (
            <small>
              {!geometryMatches
                ? 'Tree and viewport geometry do not match.'
                : !node.visible_to_user
                  ? 'Node is not visible.'
                  : !node.enabled
                    ? 'Node is disabled.'
                    : 'Node is outside the current viewport.'}
            </small>
          )}
        </div>
      </div>
    </section>
  )
}

function VisionInspector({
  controller,
  selectedDetection,
}: {
  controller: AndroidDebugController
  selectedDetection: VisionDetection | null
}) {
  const detections = controller.debug?.detections ?? []
  return (
    <section className="android-tab-inspector" aria-label="Vision Inspector">
      <header className="android-editor-section-heading">
        <strong>Detections</strong>
        <Tag minimal>{detections.length}</Tag>
      </header>
      <div className="android-detection-list">
        {detections.map((detection) => (
          <Button
            key={detection.id}
            minimal
            fill
            alignText="left"
            active={detection.id === controller.selectedDetectionId}
            onClick={() => controller.setSelectedDetectionId(detection.id)}
            onMouseEnter={() => controller.setHighlightedDetectionId(detection.id)}
            onMouseLeave={() => controller.setHighlightedDetectionId(null)}
          >
            <span>
              <strong>{detection.label}</strong>
              <small>
                x {detection.center.x.toFixed(0)} · y {detection.center.y.toFixed(0)}
              </small>
            </span>
            <Tag minimal>{(detection.confidence * 100).toFixed(1)}%</Tag>
          </Button>
        ))}
        {!detections.length && (
          <div className="android-panel-empty">No detections yet.</div>
        )}
      </div>
      <div className="android-selected-detection">
        {selectedDetection
          ? `${selectedDetection.label} · bbox ${selectedDetection.bbox.x},${selectedDetection.bbox.y}, ${selectedDetection.bbox.width}×${selectedDetection.bbox.height}`
          : 'No detection selected.'}
      </div>
    </section>
  )
}

function MacroInspector({ controller }: { controller: AndroidDebugController }) {
  const { debug, status } = controller
  return (
    <section className="android-tab-inspector" aria-label="Macro Inspector">
      <header className="android-editor-section-heading">
        <strong>Macro / Debug State</strong>
        <Tag intent={macroIntent(debug?.macro.status)} minimal>
          {debug?.macro.status ?? 'IDLE'}
        </Tag>
      </header>
      <StateRows status={status} debug={debug} />
      <Divider />
      <section className="android-decision-debug">
        <h2>Decision</h2>
        <dl>
          <div>
            <dt>Classifier</dt>
            <dd>{pretty(debug?.decision.classifier)}</dd>
          </div>
          <div>
            <dt>VLM</dt>
            <dd>{pretty(debug?.decision.vlm)}</dd>
          </div>
          <div>
            <dt>Target</dt>
            <dd>{pretty(debug?.decision.target)}</dd>
          </div>
          <div>
            <dt>Final action</dt>
            <dd>{pretty(debug?.decision.final_action)}</dd>
          </div>
          {debug?.decision.blocked_reason && (
            <div className="is-blocked">
              <dt>Blocked</dt>
              <dd>{debug.decision.blocked_reason}</dd>
            </div>
          )}
        </dl>
      </section>
    </section>
  )
}

function AndroidConsolePanel({
  controller,
  selectedDetection,
}: {
  controller: AndroidDebugController
  selectedDetection: VisionDetection | null
}) {
  const [tab, setTab] = useState<ConsoleTab>('console')
  return (
    <Card className="android-console-panel" elevation={Elevation.ONE}>
      <header className="android-card-heading">
        <div>
          <span>Bounded bottom panel</span>
          <strong>
            {tab === 'console' ? 'Console' : tab === 'vision' ? 'Vision' : 'Macro'}
          </strong>
        </div>
        <div className="android-console-tabs" role="tablist" aria-label="Bottom panel">
          {(['console', 'vision', 'macro'] as const).map((value) => (
            <Button
              key={value}
              minimal
              small
              active={tab === value}
              role="tab"
              aria-selected={tab === value}
              text={
                value === 'console'
                  ? `Console (${controller.events.length.toString()})`
                  : value === 'vision'
                    ? 'Vision'
                    : 'Macro'
              }
              onClick={() => setTab(value)}
            />
          ))}
        </div>
      </header>
      <div className="android-console-content">
        {tab === 'console' && (
          <div className="android-event-list">
            {controller.events.length ? (
              controller.events.map((event) => (
                <div key={event.id} className={`android-event-row is-${event.status}`}>
                  <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
                  <Tag minimal>{event.category}</Tag>
                  <span>{event.message}</span>
                  <small>
                    {event.latency_ms === null
                      ? event.status
                      : `${event.latency_ms.toFixed(1)} ms`}
                  </small>
                </div>
              ))
            ) : (
              <div className="android-panel-empty">No debug events yet.</div>
            )}
          </div>
        )}
        {tab === 'vision' && (
          <VisionInspector
            controller={controller}
            selectedDetection={selectedDetection}
          />
        )}
        {tab === 'macro' && <MacroInspector controller={controller} />}
      </div>
    </Card>
  )
}

function StateRows({
  status,
  debug,
}: {
  status: AndroidDebugController['status']
  debug: AndroidDebugState | null
}) {
  const rows = [
    ['Current state', debug?.state.current ?? 'unknown'],
    ['Previous state', debug?.state.previous ?? '—'],
    ['Confidence', `${((debug?.state.confidence ?? 0) * 100).toFixed(1)}%`],
    ['Detector results', (debug?.detections.length ?? 0).toString()],
    ['Macro ID', debug?.macro.id ?? '—'],
    ['Step index', (debug?.macro.step_index ?? 0).toString()],
    ['Last action', pretty(debug?.last_action)],
    ['Action result', pretty(debug?.last_action_result)],
    ['Accessibility', status?.agent?.accessibility_enabled ? 'Enabled' : 'Disabled'],
    ['Capture', status?.agent?.capture_ready ? 'Ready' : 'Not ready'],
    ['Remote control', status?.agent?.remote_control_enabled ? 'Enabled' : 'Disabled'],
    ['Rotation', `${status?.agent?.device.rotation ?? 0}°`],
    ['Agent version', status?.agent?.agent_version ?? '—'],
  ]
  return (
    <dl className="android-state-list">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd title={value}>{value}</dd>
        </div>
      ))}
    </dl>
  )
}
