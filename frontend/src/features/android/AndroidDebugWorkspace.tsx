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
} from '../../types/android-debug'
import type { VisionDetection } from '../../types/vision'
import { androidApi } from './android-api'
import { appendSampledPoint, isTapPath, mapPointerToFrame } from './pointer-gesture'
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
  pointerPath: AndroidPointerPoint[]
}

function AndroidOverlay({
  width,
  height,
  detections,
  selectedId,
  highlightedId,
  plannedPoint,
  uiBounds,
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
      {uiBounds && (
        <g className="android-ui-node-box">
          <rect
            x={uiBounds.left}
            y={uiBounds.top}
            width={uiBounds.right - uiBounds.left}
            height={uiBounds.bottom - uiBounds.top}
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
  const frameWidth =
    debug?.frame?.width ?? status?.stream?.width ?? status?.agent?.device.width ?? 0
  const frameHeight =
    debug?.frame?.height ?? status?.stream?.height ?? status?.agent?.device.height ?? 0
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
  const selectedUiBounds =
    controller.uiTree?.screen_width === frameWidth &&
    controller.uiTree.screen_height === frameHeight
      ? (selectedUiNode?.bounds ?? null)
      : null
  const [recordingPath, setRecordingPath] = useState<AndroidPointerPoint[]>([])
  const [recentPath, setRecentPath] = useState<AndroidPointerPoint[]>([])
  const activePointer = useRef<{
    id: number
    startedAt: number
    points: AndroidPointerPoint[]
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
    }, 0)
    return () => window.clearTimeout(reset)
  }, [controller.deviceId])

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
  ): { x: number; y: number } | null =>
    mapPointerToFrame(
      event.clientX,
      event.clientY,
      event.currentTarget.getBoundingClientRect(),
      frameWidth,
      frameHeight,
    )

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!controller.manualTapEnabled || !canControl || event.button !== 0) return
    const point = eventPoint(event)
    if (!point) return
    event.preventDefault()
    event.currentTarget.setPointerCapture?.(event.pointerId)
    const first = { ...point, t_ms: 0 }
    activePointer.current = {
      id: event.pointerId,
      startedAt: performance.now(),
      points: [first],
    }
    setRecordingPath([first])
  }

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    const active = activePointer.current
    if (!active || active.id !== event.pointerId) return
    const point = eventPoint(event)
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
    const mapped = eventPoint(event) ?? fallback
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
          <Tag intent={macroIntent(debug?.macro.status)} minimal>
            Macro {debug?.macro.status ?? 'IDLE'}
          </Tag>
        </div>
      </div>

      {!status?.configured && (
        <Callout intent="warning" title="Android Agent is not configured">
          Set <code>TAPBOT_ANDROID_AGENT_URL</code> and{' '}
          <code>TAPBOT_ANDROID_AGENT_TOKEN</code> on the PC backend.
        </Callout>
      )}
      {controller.error && (
        <Callout intent="danger" title="Android debug error">
          {controller.error}
        </Callout>
      )}
      {controller.notice && <Callout intent="success">{controller.notice}</Callout>}

      <div className="android-debug-grid">
        <Card className="android-live-card" elevation={Elevation.ONE}>
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

          <div
            className={`android-live-stage ${controller.manualTapEnabled ? 'is-tap-mode' : ''}`}
            style={
              frameWidth > 0 && frameHeight > 0
                ? {
                    aspectRatio: `${frameWidth.toString()} / ${frameHeight.toString()}`,
                  }
                : undefined
            }
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerCancel}
            onContextMenu={(event) => event.preventDefault()}
            role={controller.manualTapEnabled ? 'button' : undefined}
            tabIndex={controller.manualTapEnabled ? 0 : undefined}
          >
            {status?.connected ? (
              <>
                <img
                  key={imageSource}
                  src={imageSource}
                  alt="Android live screen"
                  draggable={false}
                  onError={() => controller.setStreamFailed(true)}
                />
                {frameWidth > 0 && frameHeight > 0 && (
                  <AndroidOverlay
                    width={frameWidth}
                    height={frameHeight}
                    detections={debug?.detections ?? []}
                    selectedId={controller.selectedDetectionId}
                    highlightedId={controller.highlightedDetectionId}
                    plannedPoint={plannedPoint}
                    uiBounds={selectedUiBounds}
                    pointerPath={recordingPath.length > 0 ? recordingPath : recentPath}
                  />
                )}
                <div className="android-live-badges">
                  <Tag intent={useStream ? 'success' : 'warning'} minimal>
                    {useStream ? 'MJPEG LIVE' : 'SCREENSHOT FALLBACK'}
                  </Tag>
                  {controller.manualTapEnabled && (
                    <Tag intent="warning">MANUAL CONTROL ACTIVE</Tag>
                  )}
                </div>
              </>
            ) : (
              <div className="android-screen-empty">
                {status === null ? <Spinner size={36} /> : null}
                <strong>
                  {status === null ? 'Connecting' : 'Android unavailable'}
                </strong>
                <span>{status?.error ?? 'Waiting for Android Agent status.'}</span>
              </div>
            )}
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
            {controller.streamFailed && (
              <Button
                icon="refresh"
                text="Reconnect Stream"
                onClick={controller.reconnectStream}
              />
            )}
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

        <Card className="android-state-card" elevation={Elevation.ONE}>
          <header className="android-card-heading">
            <div>
              <span>Pipeline inspection</span>
              <strong>Debug State</strong>
            </div>
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
        </Card>
      </div>

      <div className="android-debug-bottom">
        <Card className="android-detection-card" elevation={Elevation.ONE}>
          <header className="android-card-heading">
            <div>
              <span>Vision</span>
              <strong>Detections</strong>
            </div>
            <Tag round minimal>
              {debug?.detections.length ?? 0}
            </Tag>
          </header>
          <div className="android-detection-list">
            {debug?.detections.length ? (
              debug.detections.map((detection) => (
                <Button
                  key={detection.id}
                  minimal
                  fill
                  alignText="left"
                  active={detection.id === controller.selectedDetectionId}
                  onClick={() => controller.setSelectedDetectionId(detection.id)}
                  onMouseEnter={() =>
                    controller.setHighlightedDetectionId(detection.id)
                  }
                  onMouseLeave={() => controller.setHighlightedDetectionId(null)}
                >
                  <span>
                    <strong>{detection.label}</strong>
                    <small>
                      x {detection.center.x.toFixed(0)} · y{' '}
                      {detection.center.y.toFixed(0)}
                    </small>
                  </span>
                  <Tag
                    intent={detection.confidence >= 0.8 ? 'success' : 'warning'}
                    minimal
                  >
                    {(detection.confidence * 100).toFixed(1)}%
                  </Tag>
                </Button>
              ))
            ) : (
              <div className="android-panel-empty">No detections yet.</div>
            )}
          </div>
          {selected && (
            <div className="android-selected-detection">
              {selected.label} · bbox {selected.bbox.x},{selected.bbox.y},{' '}
              {selected.bbox.width}×{selected.bbox.height}
            </div>
          )}
        </Card>

        <UiTreeCard controller={controller} />

        <Card className="android-event-card" elevation={Elevation.ONE}>
          <header className="android-card-heading">
            <div>
              <span>Recent activity</span>
              <strong>Decision / Event Log</strong>
            </div>
            <Tag round minimal>
              {controller.events.length}
            </Tag>
          </header>
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
        </Card>
      </div>
    </section>
  )
}

function UiTreeCard({ controller }: { controller: AndroidDebugController }) {
  const [query, setQuery] = useState('')
  const normalized = query.trim().toLocaleLowerCase()
  const nodes = useMemo(
    () =>
      (controller.uiTree?.nodes ?? [])
        .filter((node) => {
          if (!normalized) return node.visible_to_user && node.enabled
          return [node.text, node.content_description, node.view_id_resource_name]
            .filter((value): value is string => Boolean(value))
            .some((value) => value.toLocaleLowerCase().includes(normalized))
        })
        .slice(0, 100),
    [controller.uiTree?.nodes, normalized],
  )
  const selected = controller.uiTree?.nodes.find(
    (node) => node.node_id === controller.selectedUiNodeId,
  )

  return (
    <Card className="android-ui-tree-card" elevation={Elevation.ONE}>
      <header className="android-card-heading">
        <div>
          <span>Accessibility</span>
          <strong>UI Tree</strong>
        </div>
        <div>
          <Tag intent={controller.uiTree ? 'success' : 'warning'} minimal>
            {controller.uiTree?.package_name ?? 'Unavailable'}
          </Tag>
          <Tag minimal>{controller.uiTree?.node_count ?? 0} nodes</Tag>
          {controller.uiTree?.truncated && <Tag intent="warning">TRUNCATED</Tag>}
        </div>
      </header>
      <div className="android-ui-tree-search">
        <input
          aria-label="Search UI tree"
          value={query}
          placeholder="Search text, content description, or view id"
          onChange={(event) => setQuery(event.currentTarget.value)}
        />
        {controller.uiTreeError && <span>{controller.uiTreeError}</span>}
      </div>
      <div className="android-ui-tree-layout">
        <div className="android-ui-node-list">
          {nodes.map((node) => (
            <Button
              key={node.node_id}
              minimal
              fill
              alignText="left"
              active={node.node_id === controller.selectedUiNodeId}
              onClick={() => controller.setSelectedUiNodeId(node.node_id)}
            >
              <span>
                <strong>
                  {node.text ?? node.content_description ?? node.class_name}
                </strong>
                <small>{node.view_id_resource_name ?? node.node_id}</small>
              </span>
              {node.clickable && <Tag minimal>clickable</Tag>}
            </Button>
          ))}
          {!nodes.length && <div className="android-panel-empty">No UI nodes.</div>}
        </div>
        <dl className="android-ui-node-detail">
          <div>
            <dt>Captured</dt>
            <dd>{controller.uiTree?.captured_at ?? '—'}</dd>
          </div>
          <div>
            <dt>Node</dt>
            <dd>{selected?.node_id ?? '—'}</dd>
          </div>
          <div>
            <dt>Text</dt>
            <dd>{selected?.text ?? '—'}</dd>
          </div>
          <div>
            <dt>Class</dt>
            <dd>{selected?.class_name ?? '—'}</dd>
          </div>
          <div>
            <dt>View ID</dt>
            <dd>{selected?.view_id_resource_name ?? '—'}</dd>
          </div>
          <div>
            <dt>Bounds</dt>
            <dd>
              {selected
                ? `${selected.bounds.left},${selected.bounds.top} → ${selected.bounds.right},${selected.bounds.bottom}`
                : '—'}
            </dd>
          </div>
          <div>
            <dt>Clickable</dt>
            <dd>{selected?.clickable ? 'Yes' : 'No'}</dd>
          </div>
        </dl>
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
