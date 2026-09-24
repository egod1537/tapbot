import {
  Button,
  ButtonGroup,
  Callout,
  Card,
  Divider,
  Elevation,
  Slider,
  Spinner,
  Tag,
} from '@blueprintjs/core'
import { useMemo, useState } from 'react'
import type { CameraOverlayFrame, CameraOverlayItem } from '../../types/camera'
import { CameraOverlay } from '../camera/CameraOverlay'
import { CameraSourceSelector } from '../camera/CameraSourceSelector'
import type { CameraStreamController } from '../camera/useCameraStream'
import { visionApi } from '../vision/vision-api'
import { VisionDetectionOverlay } from '../vision/VisionDetectionOverlay'
import type { RawCanonicalController } from '../vision/useRawCanonicalView'

type RawViewMode = 'raw' | 'phone-overlay'
type CanonicalViewMode = 'clean' | 'detection-overlay'

interface RawCanonicalWorkspaceProps {
  camera: CameraStreamController
  workspace: RawCanonicalController
}

function phoneOverlay(workspace: RawCanonicalController): CameraOverlayFrame | null {
  const pipelineResult = workspace.result
  const result = pipelineResult?.phone_detection
  if (!pipelineResult || !result) return null
  const items: CameraOverlayItem[] = []
  if (result.phone_bbox) {
    items.push({
      id: `yolo-phone-bbox-${result.result_id.toString()}`,
      kind: 'bbox',
      ...result.phone_bbox,
      label: 'YOLO phone',
      confidence: result.phone_bbox_confidence ?? undefined,
      color: '#8abbff',
      dashed: true,
    })
  }
  if (result.found && result.corners) {
    const points = [
      result.corners.tl,
      result.corners.tr,
      result.corners.br,
      result.corners.bl,
    ] as const
    items.push({
      id: `phone-${result.result_id.toString()}`,
      kind: 'screen-corners',
      points: [...points],
      label: 'refined screen',
      confidence: result.confidence,
      color: '#f0b429',
    })
  }
  if (result.center) {
    items.push({
      id: `phone-center-${result.result_id.toString()}`,
      kind: 'center',
      point: result.center,
      color: '#ff7373',
    })
  }
  if (items.length === 0) return null
  return {
    frameId: pipelineResult.frame_id,
    frameWidth: pipelineResult.frame.width,
    frameHeight: pipelineResult.frame.height,
    items,
  }
}

function phoneStatusLabel(workspace: RawCanonicalController): string {
  switch (workspace.phoneStatus) {
    case 'not-run':
      return 'NOT RUN'
    case 'running':
      return 'RUNNING'
    case 'found':
      return 'FOUND'
    case 'not-found':
      return 'NOT FOUND'
    case 'error':
      return 'ERROR'
  }
}

function canonicalStatusLabel(workspace: RawCanonicalController): string {
  switch (workspace.canonicalStatus) {
    case 'waiting':
      return 'WAITING'
    case 'transforming':
      return 'TRANSFORMING'
    case 'ready':
      return 'READY'
    case 'transform-failed':
      return 'TRANSFORM FAILED'
  }
}

export function RawCanonicalWorkspace({
  camera,
  workspace,
}: RawCanonicalWorkspaceProps) {
  const [rawMode, setRawMode] = useState<RawViewMode>('phone-overlay')
  const [canonicalMode, setCanonicalMode] =
    useState<CanonicalViewMode>('detection-overlay')
  const overlay = useMemo(() => phoneOverlay(workspace), [workspace])
  const result = workspace.result
  const phone = result?.phone_detection ?? null
  const frozenFrame = result?.frame ?? null
  const rawSource = frozenFrame
    ? visionApi.rawFrameUrl(frozenFrame.frame_id)
    : camera.frame?.objectUrl
  const rawWidth = frozenFrame?.width ?? camera.frame?.width
  const rawHeight = frozenFrame?.height ?? camera.frame?.height
  const canonical = result?.canonical ?? null
  const selectedDetection =
    result?.detections.find(
      (detection) => detection.id === workspace.selectedDetectionId,
    ) ?? null
  const cameraIssue = camera.error ?? camera.sourceError ?? camera.sourceStatus?.error
  const sourceOffline = camera.sourceStatus !== null && !camera.sourceStatus.connected
  const canRun = camera.frame !== null && camera.isConnected && !workspace.isRunning

  return (
    <section aria-labelledby="dual-view-title">
      <div className="focused-section-heading dual-view-heading">
        <div>
          <span>Camera → canonical pipeline</span>
          <h1 id="dual-view-title">Raw / Canonical</h1>
        </div>
        <div className="dual-view-sync-tags" aria-label="Synchronized result IDs">
          <Tag minimal>Frame #{result?.frame_id ?? '—'}</Tag>
          <Tag minimal>Phone #{phone?.result_id ?? '—'}</Tag>
          <Tag minimal>Canonical #{canonical?.result_id ?? '—'}</Tag>
          {result?.already_canonical && (
            <Tag intent="primary" minimal>
              CANONICAL SOURCE
            </Tag>
          )}
          {result && (
            <Tag minimal>
              YOLO {result.timings.object_detection_ms.toFixed(1)} ms · Refine{' '}
              {result.timings.screen_refinement_ms.toFixed(1)} ms · Phone{' '}
              {result.timings.phone_detection_ms.toFixed(1)} ms · Transform{' '}
              {result.timings.canonical_transform_ms.toFixed(1)} ms · UI{' '}
              {result.timings.ui_detection_ms.toFixed(1)} ms · Total{' '}
              {result.timings.total_ms.toFixed(1)} ms
            </Tag>
          )}
        </div>
      </div>

      <Card className="focused-panel dual-view-card" elevation={Elevation.ONE}>
        <div className="dual-view-grid">
          <article className="dual-view-pane dual-view-pane--raw">
            <header className="dual-view-pane__header">
              <div>
                <span>Input</span>
                <strong>Raw Camera</strong>
              </div>
              <div>
                <Tag
                  intent={
                    camera.isConnected
                      ? 'success'
                      : cameraIssue || sourceOffline
                        ? 'danger'
                        : 'warning'
                  }
                  minimal
                >
                  {camera.isConnected
                    ? 'CONNECTED'
                    : cameraIssue || sourceOffline
                      ? 'OFFLINE'
                      : 'CONNECTING'}
                </Tag>
                <Tag
                  intent={
                    workspace.phoneStatus === 'found'
                      ? 'success'
                      : workspace.phoneStatus === 'not-found' ||
                          workspace.phoneStatus === 'error'
                        ? 'danger'
                        : workspace.phoneStatus === 'running'
                          ? 'primary'
                          : 'none'
                  }
                  minimal
                >
                  PHONE {phoneStatusLabel(workspace)}
                </Tag>
              </div>
            </header>

            <div
              className="dual-view-stage"
              style={
                rawWidth && rawHeight
                  ? { aspectRatio: `${rawWidth.toString()} / ${rawHeight.toString()}` }
                  : undefined
              }
              aria-busy={workspace.phoneStatus === 'running'}
            >
              {rawSource ? (
                <>
                  <img
                    src={rawSource}
                    alt={
                      frozenFrame
                        ? `Frozen raw camera frame ${frozenFrame.frame_id.toString()}`
                        : `Live camera frame ${camera.frame?.frameId.toString() ?? ''}`
                    }
                  />
                  {rawMode === 'phone-overlay' && overlay && (
                    <CameraOverlay overlay={overlay} showLabels showConfidence />
                  )}
                  <div className="dual-view-stage__meta">
                    <Tag minimal>
                      {frozenFrame ? 'FROZEN RESULT FRAME' : 'LIVE PREVIEW'}
                    </Tag>
                    {rawWidth && rawHeight && (
                      <Tag minimal>
                        {rawWidth} × {rawHeight}
                      </Tag>
                    )}
                    {phone?.found && (
                      <Tag intent="warning" minimal>
                        {(phone.confidence * 100).toFixed(1)}%
                      </Tag>
                    )}
                    {phone?.phone_bbox_confidence !== null &&
                      phone?.phone_bbox_confidence !== undefined && (
                        <Tag intent="primary" minimal>
                          YOLO {(phone.phone_bbox_confidence * 100).toFixed(1)}%
                        </Tag>
                      )}
                  </div>
                  {workspace.phoneStatus === 'running' && (
                    <div className="focused-stage-state focused-stage-state--overlay">
                      <Spinner size={40} />
                      <strong>Detecting phone screen</strong>
                    </div>
                  )}
                </>
              ) : cameraIssue || sourceOffline ? (
                <Callout intent="danger" title="Camera offline">
                  {cameraIssue ?? 'The selected camera source is unavailable.'}
                </Callout>
              ) : (
                <div className="focused-stage-state">
                  <Spinner size={40} />
                  <strong>
                    {camera.sourceStatus?.connected ? 'No frame' : 'Connecting'}
                  </strong>
                  <span>Waiting for a camera frame.</span>
                </div>
              )}
            </div>

            <footer className="dual-view-pane__footer">
              {workspace.phoneStatus === 'not-found' ? (
                <Callout intent="warning" title="Phone screen not found">
                  {phone?.failure_reason ?? 'No phone-shaped quadrilateral was found.'}
                </Callout>
              ) : workspace.phoneError ? (
                <Callout intent="danger" title="Phone detection error">
                  {workspace.phoneError}
                </Callout>
              ) : (
                <span>
                  {phone?.found
                    ? `Detected by ${phone.source ?? 'unknown source'}`
                    : 'Run detection to lock a frame and locate the phone screen.'}
                </span>
              )}
            </footer>
          </article>

          <article className="dual-view-pane dual-view-pane--canonical">
            <header className="dual-view-pane__header">
              <div>
                <span>Output</span>
                <strong>Canonical View</strong>
              </div>
              <div>
                <Tag
                  intent={
                    workspace.canonicalStatus === 'ready'
                      ? 'success'
                      : workspace.canonicalStatus === 'transform-failed'
                        ? 'danger'
                        : workspace.canonicalStatus === 'transforming'
                          ? 'primary'
                          : 'none'
                  }
                  minimal
                >
                  {canonicalStatusLabel(workspace)}
                </Tag>
                {canonical && (
                  <Tag minimal>
                    {canonical.width} × {canonical.height}
                  </Tag>
                )}
              </div>
            </header>

            <div
              className="dual-view-stage"
              style={
                canonical
                  ? {
                      aspectRatio: `${canonical.width.toString()} / ${canonical.height.toString()}`,
                    }
                  : undefined
              }
              aria-busy={workspace.canonicalStatus === 'transforming'}
            >
              {workspace.canonicalStatus === 'transforming' ? (
                <div className="focused-stage-state">
                  <Spinner size={40} />
                  <strong>Creating canonical view</strong>
                  <span>Ordering corners and applying perspective transform.</span>
                </div>
              ) : workspace.canonicalStatus === 'transform-failed' ? (
                <Callout intent="danger" title="Perspective transform failed">
                  {workspace.canonicalError ?? 'Canonical image creation failed.'}
                </Callout>
              ) : workspace.canonicalStatus === 'ready' &&
                canonical &&
                result !== null ? (
                <>
                  <img
                    src={visionApi.canonicalUrl(canonical.result_id)}
                    alt={`Canonical result ${canonical.result_id.toString()}`}
                  />
                  {canonicalMode === 'detection-overlay' && (
                    <VisionDetectionOverlay
                      width={canonical.width}
                      height={canonical.height}
                      detections={result.detections}
                      selectedId={workspace.selectedDetectionId}
                      highlightedId={workspace.highlightedDetectionId}
                      onSelect={workspace.setSelectedDetectionId}
                      onHighlight={workspace.setHighlightedDetectionId}
                    />
                  )}
                </>
              ) : (
                <div className="focused-stage-state">
                  <strong>Waiting for canonical view</strong>
                  <span>
                    {workspace.phoneStatus === 'not-found'
                      ? 'A canonical image cannot be created until the phone is found.'
                      : 'Run screen detection to create a synchronized result.'}
                  </span>
                </div>
              )}
            </div>

            <div className="dual-view-detections">
              <div className="dual-view-detections__heading">
                <strong>Detections</strong>
                <Tag round minimal>
                  {result?.detections.length ?? 0}
                </Tag>
                {selectedDetection && (
                  <span>
                    Selected: {selectedDetection.label} ·{' '}
                    {(selectedDetection.confidence * 100).toFixed(1)}%
                  </span>
                )}
              </div>
              {workspace.visionError && (
                <Callout intent="danger" title="Canonical detection failed">
                  {workspace.visionError}
                </Callout>
              )}
              <div className="dual-view-detection-list">
                {!result || result.detections.length === 0 ? (
                  <span>
                    {workspace.canonicalStatus === 'ready'
                      ? 'No detections above the threshold.'
                      : 'Detection results will appear here.'}
                  </span>
                ) : (
                  result.detections.map((detection) => (
                    <Button
                      key={detection.id}
                      minimal
                      fill
                      alignText="left"
                      active={detection.id === workspace.selectedDetectionId}
                      onClick={() => workspace.setSelectedDetectionId(detection.id)}
                      onMouseEnter={() =>
                        workspace.setHighlightedDetectionId(detection.id)
                      }
                      onMouseLeave={() => workspace.setHighlightedDetectionId(null)}
                    >
                      <span>
                        <strong>{detection.label}</strong>
                        <small>
                          center {detection.center.x.toFixed(1)},{' '}
                          {detection.center.y.toFixed(1)}
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
                )}
              </div>
            </div>
          </article>
        </div>

        <Divider />

        <div className="dual-view-controls">
          <CameraSourceSelector camera={camera} />
          <div className="dual-view-control-groups">
            <label>
              <span className="focused-control-label">Raw view</span>
              <ButtonGroup>
                <Button
                  active={rawMode === 'raw'}
                  text="Raw"
                  onClick={() => setRawMode('raw')}
                />
                <Button
                  active={rawMode === 'phone-overlay'}
                  text="Phone Overlay"
                  onClick={() => setRawMode('phone-overlay')}
                />
              </ButtonGroup>
            </label>
            <label>
              <span className="focused-control-label">Canonical view</span>
              <ButtonGroup>
                <Button
                  active={canonicalMode === 'clean'}
                  text="Clean"
                  onClick={() => setCanonicalMode('clean')}
                />
                <Button
                  active={canonicalMode === 'detection-overlay'}
                  text="Detection Overlay"
                  onClick={() => setCanonicalMode('detection-overlay')}
                />
              </ButtonGroup>
            </label>
          </div>
          <div className="dual-view-run-controls">
            <div className="dual-view-threshold">
              <span className="focused-control-label">
                Detection threshold · {Math.round(workspace.confidenceThreshold * 100)}%
              </span>
              <Slider
                min={0}
                max={1}
                stepSize={0.01}
                labelRenderer={false}
                value={workspace.confidenceThreshold}
                onChange={workspace.setConfidenceThreshold}
              />
            </div>
            <Button
              icon="search"
              intent="primary"
              large
              text={workspace.isRunning ? 'Running Detection' : 'Run Screen Detection'}
              loading={workspace.isRunning}
              disabled={!canRun}
              onClick={() => void workspace.run()}
            />
          </div>
        </div>
      </Card>
    </section>
  )
}
