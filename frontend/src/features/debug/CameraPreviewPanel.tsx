import { useMemo, useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { Panel } from '../../components/Panel'
import { CameraIcon } from '../../components/icons'
import { CameraOverlay } from '../camera/CameraOverlay'
import { CameraSourceSelector } from '../camera/CameraSourceSelector'
import { buildDebugOverlayFixture } from '../camera/debug-overlay-fixture'
import type { CameraStreamController } from '../camera/useCameraStream'

type CameraView = 'raw' | 'overlay'

interface CameraPreviewPanelProps {
  camera: CameraStreamController
}

export function CameraPreviewPanel({ camera }: CameraPreviewPanelProps) {
  const [view, setView] = useState<CameraView>('overlay')
  const [showLabels, setShowLabels] = useState(true)
  const [showConfidence, setShowConfidence] = useState(true)
  const [savedFrameId, setSavedFrameId] = useState<number | null>(null)

  const overlay = useMemo(
    () =>
      camera.frame
        ? buildDebugOverlayFixture(
            camera.frame.frameId,
            camera.frame.width,
            camera.frame.height,
          )
        : null,
    [camera.frame],
  )

  const captureScreenshot = () => {
    const frameId = camera.saveScreenshot()
    if (frameId !== null) setSavedFrameId(frameId)
  }

  return (
    <Panel
      title="Camera Preview"
      eyebrow="Live input / 01"
      className="camera-panel"
      actions={
        <>
          <span
            className={
              camera.isConnected
                ? 'camera-connection is-connected'
                : 'camera-connection'
            }
          >
            {camera.isConnected ? 'Live' : 'Offline'}
          </span>
          <span className="panel-metric panel-metric--resolution">
            {camera.frame
              ? `${camera.frame.width.toString()} × ${camera.frame.height.toString()}`
              : '— × —'}
          </span>
          <span className="panel-metric">
            {camera.fps ? `${camera.fps.toFixed(1)} FPS` : '— FPS'}
          </span>
        </>
      }
    >
      <div className="camera-toolbar">
        <div className="view-switch" aria-label="Camera debug view">
          <button
            type="button"
            className={view === 'raw' ? 'is-active' : undefined}
            aria-pressed={view === 'raw'}
            onClick={() => setView('raw')}
          >
            Raw
          </button>
          <button
            type="button"
            className={view === 'overlay' ? 'is-active' : undefined}
            aria-pressed={view === 'overlay'}
            onClick={() => setView('overlay')}
          >
            Overlay
          </button>
        </div>

        <div className="overlay-toggles">
          <label>
            <input
              type="checkbox"
              checked={showLabels}
              onChange={(event) => setShowLabels(event.target.checked)}
            />
            <span>Labels</span>
          </label>
          <label>
            <input
              type="checkbox"
              checked={showConfidence}
              onChange={(event) => setShowConfidence(event.target.checked)}
            />
            <span>Confidence</span>
          </label>
        </div>

        <button
          type="button"
          className="screenshot-button"
          disabled={!camera.frame}
          onClick={captureScreenshot}
        >
          <CameraIcon />
          Screenshot
        </button>
      </div>

      <CameraSourceSelector camera={camera} />

      <div className="camera-stage">
        {camera.frame ? (
          <>
            <img
              src={camera.frame.objectUrl}
              alt={`Camera frame ${camera.frame.frameId.toString()}`}
            />
            {view === 'overlay' && overlay && (
              <CameraOverlay
                overlay={overlay}
                showLabels={showLabels}
                showConfidence={showConfidence}
              />
            )}
            {view === 'overlay' && (
              <span className="demo-overlay-badge">Debug overlay</span>
            )}
          </>
        ) : (
          <div className="preview-surface">
            <div className="preview-grid" aria-hidden="true" />
            <EmptyState
              icon={<CameraIcon />}
              title={camera.error ? 'Camera is unavailable' : 'Connecting to camera'}
              description={
                camera.error
                  ? camera.error
                  : 'Waiting for the first JPEG frame from the backend.'
              }
            />
          </div>
        )}

        {camera.frame && camera.error && (
          <div className="stale-frame-message" role="status">
            <span>Connection lost · showing frame #{camera.frame.frameId}</span>
            <button type="button" onClick={camera.retry}>
              Retry
            </button>
          </div>
        )}

        <span className="frame-corner frame-corner--tl" />
        <span className="frame-corner frame-corner--tr" />
        <span className="frame-corner frame-corner--bl" />
        <span className="frame-corner frame-corner--br" />
      </div>

      <div className="camera-footer">
        <span>
          Frame <strong>#{camera.frame?.frameId ?? '—'}</strong>
        </span>
        <span className="camera-footer__timestamp">
          {camera.frame?.capturedAt
            ? new Date(camera.frame.capturedAt).toLocaleTimeString()
            : 'No frame received'}
        </span>
        <span className="screenshot-result" aria-live="polite">
          {savedFrameId
            ? `Saved frame #${savedFrameId.toString()}`
            : 'Screenshot ready'}
        </span>
      </div>
    </Panel>
  )
}
