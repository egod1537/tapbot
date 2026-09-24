import {
  Button,
  ButtonGroup,
  Callout,
  Card,
  Divider,
  Elevation,
  Spinner,
  Tag,
} from '@blueprintjs/core'
import type { MouseEvent } from 'react'
import { useMemo } from 'react'
import type { AndroidDebugState } from '../../types/android-debug'
import type { VisionDetection } from '../../types/vision'
import { androidApi } from './android-api'
import type { AndroidDebugController } from './useAndroidDebug'

interface AndroidDebugWorkspaceProps {
  controller: AndroidDebugController
}

interface AndroidOverlayProps {
  width: number
  height: number
  detections: VisionDetection[]
  selectedId: string | null
  highlightedId: string | null
  plannedPoint: { x: number; y: number } | null
}

function AndroidOverlay({
  width,
  height,
  detections,
  selectedId,
  highlightedId,
  plannedPoint,
}: AndroidOverlayProps) {
  const scale = Math.max(width, height) / 900
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

export function AndroidDebugWorkspace({ controller }: AndroidDebugWorkspaceProps) {
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
    ? androidApi.streamUrl(controller.streamNonce)
    : androidApi.screenshotUrl(debug?.frame?.frame_id ?? controller.streamNonce)
  const plannedPoint = debug?.decision.target?.screen ?? null
  const selected = useMemo(
    () =>
      debug?.detections.find(
        (detection) => detection.id === controller.selectedDetectionId,
      ) ?? null,
    [controller.selectedDetectionId, debug?.detections],
  )

  const handleScreenClick = (event: MouseEvent<HTMLDivElement>) => {
    if (
      !controller.manualTapEnabled ||
      !canControl ||
      frameWidth <= 0 ||
      frameHeight <= 0
    ) {
      return
    }
    const bounds = event.currentTarget.getBoundingClientRect()
    const scale = Math.min(bounds.width / frameWidth, bounds.height / frameHeight)
    const renderedWidth = frameWidth * scale
    const renderedHeight = frameHeight * scale
    const offsetX = (bounds.width - renderedWidth) / 2
    const offsetY = (bounds.height - renderedHeight) / 2
    const x = (event.clientX - bounds.left - offsetX) / scale
    const y = (event.clientY - bounds.top - offsetY) / scale
    if (x < 0 || y < 0 || x >= frameWidth || y >= frameHeight) return
    void controller.tap(x, y)
  }

  return (
    <section className="android-debug-workspace" aria-labelledby="android-debug-title">
      <div className="android-debug-heading">
        <div>
          <span>PC-controlled canonical screen</span>
          <h1 id="android-debug-title">Android Remote Debug</h1>
        </div>
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
            onClick={handleScreenClick}
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
                  />
                )}
                <div className="android-live-badges">
                  <Tag intent={useStream ? 'success' : 'warning'} minimal>
                    {useStream ? 'MJPEG LIVE' : 'SCREENSHOT FALLBACK'}
                  </Tag>
                  {controller.manualTapEnabled && (
                    <Tag intent="warning">TAP MODE ACTIVE</Tag>
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
              text={controller.manualTapEnabled ? 'Tap Mode On' : 'Tap Mode'}
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
