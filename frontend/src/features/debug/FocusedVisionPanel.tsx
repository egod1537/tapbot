import {
  Button,
  Callout,
  Card,
  Divider,
  Elevation,
  HTMLSelect,
  Slider,
  Spinner,
  Tag,
} from '@blueprintjs/core'
import { useSystemStatus } from '../../app/system-status'
import type { VisionFrameMetadata } from '../../types/vision'
import { VisionDetectionOverlay } from '../vision/VisionDetectionOverlay'
import { visionApi } from '../vision/vision-api'
import type { VisionDebugController } from '../vision/useVisionDebug'

interface FocusedVisionPanelProps {
  vision: VisionDebugController
  canSaveFrame: boolean
}

function frameLabel(frame: VisionFrameMetadata): string {
  const capturedAt = new Date(frame.captured_at)
  const time = Number.isNaN(capturedAt.getTime())
    ? frame.captured_at
    : capturedAt.toLocaleTimeString()
  return `Frame ${frame.frame_id.toString()} · ${time}`
}

export function FocusedVisionPanel({ vision, canSaveFrame }: FocusedVisionPanelProps) {
  const system = useSystemStatus()
  const result = vision.currentResult
  const resultStatus = vision.isRunning
    ? 'RUNNING'
    : result
      ? `${result.detections.length.toString()} DETECTIONS`
      : 'READY'

  return (
    <section aria-labelledby="vision-panel-title">
      <div className="focused-section-heading">
        <div>
          <span>OpenCV pipeline</span>
          <h1 id="vision-panel-title">Vision</h1>
        </div>
        <Tag
          intent={vision.error ? 'danger' : vision.isRunning ? 'primary' : 'none'}
          minimal
        >
          {resultStatus}
        </Tag>
      </div>

      <Card className="focused-panel focused-vision-card" elevation={Elevation.ONE}>
        {vision.error && (
          <Callout
            className="focused-inline-callout"
            intent="danger"
            title="Vision request failed"
          >
            {vision.error}
            <Button minimal small icon="refresh" text="Retry" onClick={vision.retry} />
          </Callout>
        )}

        {system.calibrationMissing && !result && !vision.error && (
          <Callout className="focused-inline-callout" intent="warning">
            An active calibration profile may be required before detection can run.
          </Callout>
        )}

        <div className="focused-vision-grid">
          <div className="focused-vision-preview">
            <div className="focused-subheading">
              <strong>Rectified / Vision Preview</strong>
              {result && (
                <span>
                  {result.rectified.width} × {result.rectified.height}
                </span>
              )}
            </div>
            <div
              className="focused-vision-stage"
              style={
                result
                  ? {
                      aspectRatio: `${result.rectified.width.toString()} / ${result.rectified.height.toString()}`,
                    }
                  : undefined
              }
              aria-busy={vision.isRunning}
            >
              {vision.isRunning && (
                <div className="focused-stage-state focused-stage-state--overlay">
                  <Spinner size={42} />
                  <strong>Running detectors</strong>
                </div>
              )}
              {result ? (
                <>
                  <img
                    src={visionApi.rectifiedUrl(result.result_id)}
                    alt={`Rectified vision result ${result.result_id.toString()}`}
                  />
                  <VisionDetectionOverlay
                    width={result.rectified.width}
                    height={result.rectified.height}
                    detections={result.detections}
                    selectedId={vision.selectedDetectionId}
                    highlightedId={vision.highlightedDetectionId}
                    onSelect={vision.setSelectedDetectionId}
                    onHighlight={vision.setHighlightedDetectionId}
                  />
                </>
              ) : (
                <div className="focused-stage-state">
                  <strong>
                    {vision.isLoading
                      ? 'Loading vision workspace'
                      : vision.frames.length === 0
                        ? 'No saved frame'
                        : 'No detection result'}
                  </strong>
                  <span>
                    {vision.frames.length === 0
                      ? 'Save the current camera frame to begin.'
                      : 'Select a saved frame and run detection.'}
                  </span>
                </div>
              )}
            </div>
          </div>

          <aside className="focused-detections" aria-label="Detections">
            <div className="focused-subheading">
              <strong>Detections</strong>
              <Tag round minimal>
                {result?.detections.length ?? 0}
              </Tag>
            </div>
            <Divider />
            <div className="focused-detection-list">
              {!result || result.detections.length === 0 ? (
                <div className="focused-list-empty">
                  {result
                    ? 'No detections above the selected threshold.'
                    : 'Detection results will appear here.'}
                </div>
              ) : (
                result.detections.map((detection) => (
                  <Button
                    key={detection.id}
                    className="focused-detection-row"
                    active={detection.id === vision.selectedDetectionId}
                    alignText="left"
                    fill
                    minimal
                    onClick={() => vision.setSelectedDetectionId(detection.id)}
                    onMouseEnter={() => vision.setHighlightedDetectionId(detection.id)}
                    onMouseLeave={() => vision.setHighlightedDetectionId(null)}
                  >
                    <span className="focused-detection-row__main">
                      <strong>{detection.label}</strong>
                      <Tag
                        intent={detection.confidence >= 0.8 ? 'success' : 'warning'}
                        minimal
                      >
                        {(detection.confidence * 100).toFixed(1)}%
                      </Tag>
                    </span>
                    <span className="focused-detection-row__secondary">
                      center {detection.center.x.toFixed(1)},{' '}
                      {detection.center.y.toFixed(1)} · bbox {detection.bbox.x},{' '}
                      {detection.bbox.y}, {detection.bbox.width} ×{' '}
                      {detection.bbox.height}
                    </span>
                  </Button>
                ))
              )}
            </div>
          </aside>
        </div>

        <Divider />

        <div className="focused-vision-controls">
          <div className="focused-vision-actions">
            <Button
              icon="floppy-disk"
              text={vision.isSaving ? 'Saving Frame' : 'Save Frame'}
              loading={vision.isSaving}
              disabled={vision.isRunning || !canSaveFrame}
              onClick={vision.saveFrame}
            />
            <Button
              icon="play"
              intent="primary"
              text={vision.isRunning ? 'Running Detection' : 'Run Detection'}
              loading={vision.isRunning}
              disabled={vision.selectedFrameId === null || vision.isSaving}
              onClick={vision.runSelected}
            />
          </div>

          <label className="focused-frame-select">
            <span className="focused-control-label">Saved frame</span>
            <HTMLSelect
              fill
              value={vision.selectedFrameId ?? ''}
              disabled={vision.frames.length === 0 || vision.isRunning}
              onChange={(event) =>
                vision.setSelectedFrameId(Number(event.currentTarget.value))
              }
            >
              {vision.frames.length === 0 && <option value="">No saved frames</option>}
              {vision.frames.map((frame) => (
                <option key={frame.frame_id} value={frame.frame_id}>
                  {frameLabel(frame)}
                </option>
              ))}
            </HTMLSelect>
          </label>

          <div className="focused-threshold">
            <div>
              <span className="focused-control-label">Confidence threshold</span>
              <strong>{Math.round(vision.confidenceThreshold * 100)}%</strong>
            </div>
            <Slider
              min={0}
              max={1}
              stepSize={0.01}
              labelStepSize={0.25}
              labelRenderer={(value) => `${Math.round(value * 100).toString()}%`}
              value={vision.confidenceThreshold}
              onChange={vision.setConfidenceThreshold}
            />
          </div>
        </div>
      </Card>
    </section>
  )
}
