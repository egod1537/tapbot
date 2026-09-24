import {
  Button,
  ButtonGroup,
  Callout,
  Card,
  Elevation,
  Spinner,
  Tag,
} from '@blueprintjs/core'
import { useMemo, useState } from 'react'
import type { CameraOverlayFrame, CameraOverlayItem } from '../../types/camera'
import { CameraOverlay } from '../camera/CameraOverlay'
import { CameraSourceSelector } from '../camera/CameraSourceSelector'
import type { CameraStreamController } from '../camera/useCameraStream'
import type { VisionDebugController } from '../vision/useVisionDebug'

type CameraView = 'raw' | 'overlay'

interface FocusedCameraPanelProps {
  camera: CameraStreamController
  vision: VisionDebugController
}

function buildOverlay(
  camera: CameraStreamController,
  vision: VisionDebugController,
): CameraOverlayFrame | null {
  const frame = camera.frame
  if (!frame) return null

  const items: CameraOverlayItem[] = []
  const result = vision.currentResult
  const resultMatchesFrame =
    result?.rectified.width === frame.width && result.rectified.height === frame.height

  if (resultMatchesFrame) {
    items.push(
      ...result.detections.map((detection): CameraOverlayItem => ({
        id: `detection-${detection.id}`,
        kind: 'bbox',
        label: detection.label,
        confidence: detection.confidence,
        color: '#4c90f0',
        ...detection.bbox,
      })),
    )
  } else {
    items.push(
      ...(camera.sourceStatus?.mock_graph?.available_hotspots ?? []).map(
        (hotspot): CameraOverlayItem => ({
          id: `hotspot-${hotspot.id}`,
          kind: 'bbox',
          label: `${hotspot.label} → ${hotspot.next_state}`,
          color: '#8abbff',
          x: hotspot.x,
          y: hotspot.y,
          width: hotspot.width,
          height: hotspot.height,
        }),
      ),
    )
  }

  return {
    frameId: frame.frameId,
    frameWidth: frame.width,
    frameHeight: frame.height,
    items,
  }
}

export function FocusedCameraPanel({ camera, vision }: FocusedCameraPanelProps) {
  const [view, setView] = useState<CameraView>('overlay')
  const overlay = useMemo(() => buildOverlay(camera, vision), [camera, vision])
  const sourceOffline = camera.sourceStatus !== null && !camera.sourceStatus.connected
  const cameraIssue = camera.error ?? camera.sourceError ?? camera.sourceStatus?.error
  const statusIntent = camera.isConnected
    ? 'success'
    : cameraIssue || sourceOffline
      ? 'danger'
      : 'warning'

  return (
    <section aria-labelledby="camera-panel-title">
      <div className="focused-section-heading">
        <div>
          <span>Live input</span>
          <h1 id="camera-panel-title">Camera</h1>
        </div>
        <Tag intent={statusIntent} minimal>
          {camera.isConnected
            ? 'CONNECTED'
            : cameraIssue || sourceOffline
              ? 'OFFLINE'
              : 'LOADING'}
        </Tag>
      </div>

      <Card className="focused-panel focused-camera-card" elevation={Elevation.ONE}>
        <div
          className="focused-camera-stage"
          aria-busy={!camera.frame && !cameraIssue && !sourceOffline}
        >
          {camera.frame ? (
            <>
              <img
                src={camera.frame.objectUrl}
                alt={`Camera frame ${camera.frame.frameId.toString()}`}
              />
              {view === 'overlay' && overlay && overlay.items.length > 0 && (
                <CameraOverlay overlay={overlay} showLabels showConfidence />
              )}
              <div className="focused-frame-meta">
                <Tag minimal>Frame #{camera.frame.frameId}</Tag>
                <Tag minimal>
                  {camera.frame.width} × {camera.frame.height}
                </Tag>
                {camera.fps !== null && <Tag minimal>{camera.fps.toFixed(1)} FPS</Tag>}
              </div>
            </>
          ) : cameraIssue || sourceOffline ? (
            <Callout
              className="focused-stage-state"
              intent="danger"
              title="Camera unavailable"
            >
              <p>{cameraIssue ?? 'The selected source is offline.'}</p>
              <Button icon="repeat" text="Reconnect" onClick={camera.retry} />
            </Callout>
          ) : (
            <div className="focused-stage-state">
              <Spinner size={42} />
              <strong>
                {camera.sourceStatus?.connected
                  ? 'No frame received'
                  : 'Connecting to camera'}
              </strong>
              <span>Waiting for the first frame from the backend.</span>
            </div>
          )}
        </div>

        {camera.frame && camera.error && (
          <Callout className="focused-inline-callout" intent="warning">
            Connection lost. The last received frame remains visible.
            <Button minimal small icon="repeat" text="Retry" onClick={camera.retry} />
          </Callout>
        )}

        <div className="focused-camera-controls">
          <CameraSourceSelector camera={camera} />
          <div className="focused-view-control">
            <span className="focused-control-label">View</span>
            <ButtonGroup>
              <Button
                active={view === 'raw'}
                text="Raw"
                onClick={() => setView('raw')}
              />
              <Button
                active={view === 'overlay'}
                text="Overlay"
                onClick={() => setView('overlay')}
              />
            </ButtonGroup>
          </div>
        </div>
      </Card>
    </section>
  )
}
