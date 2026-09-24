import { EmptyState } from '../../components/EmptyState'
import { Panel } from '../../components/Panel'
import type { VisionFrameMetadata } from '../../types/vision'
import { visionApi } from '../vision/vision-api'
import { VisionDetectionOverlay } from '../vision/VisionDetectionOverlay'
import { useVisionDebug } from '../vision/useVisionDebug'

function shortTimestamp(value: string): string {
  const timestamp = new Date(value)
  return Number.isNaN(timestamp.getTime()) ? value : timestamp.toLocaleString()
}

function frameLabel(frame: VisionFrameMetadata): string {
  const captured = new Date(frame.captured_at)
  const time = Number.isNaN(captured.getTime())
    ? frame.captured_at
    : captured.toLocaleTimeString()
  return `Frame ${frame.frame_id.toString()} · ${time}`
}

export function VisionPreviewPanel() {
  const vision = useVisionDebug()
  const result = vision.currentResult
  const selectedDetection =
    result?.detections.find(
      (detection) => detection.id === vision.selectedDetectionId,
    ) ?? null

  return (
    <Panel
      title="Vision Debug"
      eyebrow="OpenCV detector / 03"
      className="vision-panel vision-debug-panel"
      actions={
        <span className={result ? 'mode-chip' : 'mode-chip mode-chip--muted'}>
          {vision.isRunning
            ? 'Processing'
            : result
              ? `${result.detections.length.toString()} detections`
              : 'Waiting'}
        </span>
      }
    >
      <div className="vision-toolbar">
        <label>
          <span>Saved frame</span>
          <select
            value={vision.selectedFrameId ?? ''}
            disabled={vision.frames.length === 0 || vision.isRunning}
            onChange={(event) => vision.setSelectedFrameId(Number(event.target.value))}
          >
            {vision.frames.map((frame) => (
              <option key={frame.frame_id} value={frame.frame_id}>
                {frameLabel(frame)}
              </option>
            ))}
          </select>
        </label>
        <div className="vision-toolbar__actions">
          <button
            type="button"
            className="vision-button"
            disabled={vision.isSaving || vision.isRunning}
            onClick={vision.saveAndRun}
          >
            {vision.isSaving ? 'Saving…' : 'Save live frame'}
          </button>
          <button
            type="button"
            className="vision-button is-primary"
            disabled={
              vision.selectedFrameId === null || vision.isRunning || vision.isSaving
            }
            onClick={vision.runSelected}
          >
            {vision.isRunning ? 'Running…' : 'Run detectors'}
          </button>
        </div>
      </div>

      <div className="vision-filters">
        <div className="vision-detector-filters">
          <span>Detector filter</span>
          {vision.capabilities?.detectors.map((detector) => (
            <label key={detector.type} title={detector.type}>
              <input
                type="checkbox"
                checked={vision.enabledDetectorTypes.includes(detector.type)}
                onChange={() => vision.toggleDetector(detector.type)}
              />
              <span>{detector.name}</span>
              <code>{detector.type}</code>
            </label>
          ))}
        </div>
        <label className="vision-threshold">
          <span>
            Confidence threshold
            <strong>{Math.round(vision.confidenceThreshold * 100).toString()}%</strong>
          </span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={vision.confidenceThreshold}
            onChange={(event) =>
              vision.setConfidenceThreshold(Number(event.target.value))
            }
          />
        </label>
      </div>

      {vision.error && (
        <div className="vision-error" role="alert">
          <span>{vision.error}</span>
          <button type="button" onClick={vision.retry}>
            Retry
          </button>
        </div>
      )}

      {result ? (
        <>
          <div className="vision-frame-metadata">
            <div>
              <span>Frame ID</span>
              <strong>#{result.frame.frame_id}</strong>
            </div>
            <div>
              <span>Captured at</span>
              <strong>{shortTimestamp(result.frame.captured_at)}</strong>
            </div>
            <div>
              <span>Camera resolution</span>
              <strong>
                {result.frame.width} × {result.frame.height}
              </strong>
            </div>
            <div>
              <span>Rectified resolution</span>
              <strong>
                {result.rectified.width} × {result.rectified.height}
              </strong>
            </div>
          </div>

          <div className="vision-debug-layout">
            <div className="vision-image-comparison">
              <figure>
                <figcaption>
                  <span>Input</span>
                  Raw camera frame
                </figcaption>
                <div
                  className="vision-image-stage"
                  style={{
                    aspectRatio: `${result.frame.width} / ${result.frame.height}`,
                  }}
                >
                  <img
                    src={visionApi.rawFrameUrl(result.frame.frame_id)}
                    alt={`Raw camera frame ${result.frame.frame_id.toString()}`}
                  />
                </div>
              </figure>

              <figure>
                <figcaption>
                  <span>Output</span>
                  Rectified + detection overlay
                </figcaption>
                <div
                  className="vision-image-stage"
                  style={{
                    aspectRatio: `${result.rectified.width} / ${result.rectified.height}`,
                  }}
                >
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
                </div>
              </figure>
            </div>

            <aside className="vision-detection-inspector">
              <header>
                <div>
                  <span>Detection list</span>
                  <strong>{result.detections.length}</strong>
                </div>
                <small>Hover a row to highlight its overlay</small>
              </header>
              <div className="vision-detection-list">
                {result.detections.length === 0 ? (
                  <p>No detections above the current threshold.</p>
                ) : (
                  result.detections.map((detection) => (
                    <button
                      type="button"
                      className={
                        detection.id === vision.selectedDetectionId
                          ? 'is-selected'
                          : undefined
                      }
                      key={detection.id}
                      onClick={() => vision.setSelectedDetectionId(detection.id)}
                      onMouseEnter={() =>
                        vision.setHighlightedDetectionId(detection.id)
                      }
                      onMouseLeave={() => vision.setHighlightedDetectionId(null)}
                    >
                      <span className="vision-detection-list__title">
                        <strong>{detection.label}</strong>
                        <em>{(detection.confidence * 100).toFixed(1)}%</em>
                      </span>
                      <span>
                        x {detection.bbox.x} · y {detection.bbox.y} · w{' '}
                        {detection.bbox.width} · h {detection.bbox.height}
                      </span>
                      <code>{detection.detector_type}</code>
                    </button>
                  ))
                )}
              </div>

              <div className="vision-detection-detail">
                <span>Selected detection</span>
                {selectedDetection ? (
                  <dl>
                    <div>
                      <dt>Label</dt>
                      <dd>{selectedDetection.label}</dd>
                    </div>
                    <div>
                      <dt>Detector</dt>
                      <dd>{selectedDetection.detector_name}</dd>
                    </div>
                    <div>
                      <dt>Center</dt>
                      <dd>
                        {selectedDetection.center.x.toFixed(1)},{' '}
                        {selectedDetection.center.y.toFixed(1)}
                      </dd>
                    </div>
                    <div>
                      <dt>BBox</dt>
                      <dd>
                        {selectedDetection.bbox.x}, {selectedDetection.bbox.y},{' '}
                        {selectedDetection.bbox.width} × {selectedDetection.bbox.height}
                      </dd>
                    </div>
                    <div>
                      <dt>Confidence</dt>
                      <dd>{selectedDetection.confidence.toFixed(4)}</dd>
                    </div>
                    <div>
                      <dt>Source</dt>
                      <dd>{selectedDetection.detector_type}</dd>
                    </div>
                  </dl>
                ) : (
                  <p>Select a detection from the list or overlay.</p>
                )}
              </div>
            </aside>
          </div>

          {vision.previousResult && (
            <div className="vision-previous-result">
              <div>
                <span>Previous result retained for comparison</span>
                <strong>
                  Frame #{vision.previousResult.frame.frame_id} ·{' '}
                  {vision.previousResult.detections.length} detections · threshold{' '}
                  {Math.round(vision.previousResult.confidence_threshold * 100)}%
                </strong>
              </div>
              <img
                src={visionApi.rectifiedUrl(vision.previousResult.result_id)}
                alt={`Previous result ${vision.previousResult.result_id.toString()}`}
              />
              <button type="button" onClick={vision.clearPrevious}>
                Dismiss
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="vision-empty">
          <EmptyState
            title={
              vision.isLoading
                ? 'Preparing vision workspace'
                : 'Vision result unavailable'
            }
            description={
              vision.isLoading
                ? 'Saving a camera frame and loading detector capabilities.'
                : 'A camera frame and active calibration profile are required.'
            }
          />
        </div>
      )}
    </Panel>
  )
}
