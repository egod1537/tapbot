import { EmptyState } from '../../components/EmptyState'
import { Panel } from '../../components/Panel'
import { JsonSyntaxHighlight } from '../model/JsonSyntaxHighlight'
import { LazyJsonDetails } from '../model/LazyJsonDetails'
import { modelApi } from '../model/model-api'
import { useModelDebug } from '../model/useModelDebug'

function gateClass(passed: boolean | null): string {
  if (passed === true) return 'is-passed'
  if (passed === false) return 'is-blocked'
  return 'is-skipped'
}

export function ModelDebugPanel() {
  const model = useModelDebug()
  const result = model.result
  const decision = result?.decision
  const gates = result
    ? [
        { label: 'Schema valid', value: result.gates.schema_valid },
        { label: 'Confidence threshold', value: result.gates.confidence_threshold },
        { label: 'Target resolved', value: result.gates.target_resolved },
        { label: 'Action created', value: result.gates.action_created },
      ]
    : []

  return (
    <Panel
      title="Local Model Debug"
      eyebrow="Structured decision boundary / 04"
      className="model-panel model-debug-panel"
      actions={
        <span
          className={
            model.status?.connected
              ? 'model-connection is-connected'
              : 'model-connection'
          }
        >
          {model.status?.connected ? 'Connected' : 'Offline'}
        </span>
      }
    >
      <div className="model-status-grid">
        <div>
          <span>Provider</span>
          <strong>{model.status?.provider ?? '—'}</strong>
        </div>
        <div>
          <span>Model</span>
          <strong>{model.status?.model_name ?? '—'}</strong>
        </div>
        <div>
          <span>Connection</span>
          <strong>{model.status?.connected ? 'Online' : 'Unavailable'}</strong>
        </div>
        <div>
          <span>Model latency</span>
          <strong>
            {model.status?.last_latency_ms === null ||
            model.status?.last_latency_ms === undefined
              ? 'Not measured'
              : `${model.status.last_latency_ms.toFixed(1)} ms`}
          </strong>
        </div>
      </div>

      <div className="model-run-toolbar">
        <label>
          <span>Replay input</span>
          <select
            value={model.selectedFrameId ?? ''}
            disabled={model.isRunning}
            onChange={(event) => {
              model.setSelectedFrameId(
                event.target.value === '' ? null : Number(event.target.value),
              )
            }}
          >
            <option value="">Current live frame</option>
            {model.frames.map((frame) => (
              <option value={frame.frame_id} key={frame.frame_id}>
                Saved frame #{frame.frame_id} ·{' '}
                {new Date(frame.captured_at).toLocaleTimeString()}
              </option>
            ))}
          </select>
        </label>
        <div className="model-run-boundary">
          <span aria-hidden="true">◆</span>
          <p>
            <strong>Analysis only</strong>
            Robot execution is disabled for every Model Debug replay.
          </p>
        </div>
        <button
          type="button"
          className="model-run-button"
          disabled={model.isRunning || model.isLoading}
          onClick={model.run}
        >
          {model.isRunning ? 'Running model…' : 'Run model only'}
        </button>
      </div>

      {model.error && (
        <div className="model-error" role="alert">
          <span>{model.error}</span>
          <button type="button" onClick={model.retry}>
            Retry status
          </button>
        </div>
      )}

      {result ? (
        <>
          {result.gates.schema_valid.passed === false && (
            <div className="model-invalid-response" role="alert">
              <strong>Invalid model response blocked</strong>
              <span>{result.error ?? result.gates.schema_valid.reason}</span>
            </div>
          )}

          <div className="model-debug-layout">
            <section className="model-input-column">
              <header>
                <span>Model input screenshot</span>
                <code>
                  {result.input.width} × {result.input.height}
                </code>
              </header>
              <div
                className="model-input-frame"
                style={{
                  aspectRatio: `${result.input.width} / ${result.input.height}`,
                }}
              >
                <img
                  src={modelApi.inputImageUrl(result.run_id)}
                  alt={`Model input for run ${result.run_id.toString()}`}
                />
              </div>
              <div className="model-image-id" title={result.input.image_id}>
                {result.input.image_id}
              </div>

              <details className="model-context" open>
                <summary>Current context</summary>
                <JsonSyntaxHighlight value={result.context} />
              </details>
            </section>

            <section className="model-decision-column">
              <header>
                <span>Parsed decision</span>
                <code>{result.status}</code>
              </header>
              {decision ? (
                <div className="model-decision-card">
                  <dl>
                    <div>
                      <dt>State</dt>
                      <dd>{decision.state}</dd>
                    </div>
                    <div>
                      <dt>Action</dt>
                      <dd>{decision.action}</dd>
                    </div>
                    <div>
                      <dt>Target</dt>
                      <dd>{decision.target ?? 'None'}</dd>
                    </div>
                    <div>
                      <dt>Confidence</dt>
                      <dd>{(decision.confidence * 100).toFixed(1)}%</dd>
                    </div>
                  </dl>
                  <div className="model-confidence">
                    <span
                      style={{ width: `${(decision.confidence * 100).toString()}%` }}
                    />
                    <i
                      style={{
                        left: `${((model.status?.confidence_threshold ?? 0.8) * 100).toString()}%`,
                      }}
                    />
                  </div>
                  <p>{decision.reason}</p>
                </div>
              ) : (
                <div className="model-no-decision">
                  Structured decision was not created. Inspect the raw response and
                  schema gate.
                </div>
              )}

              <div className="model-resolution">
                <div>
                  <span>Resolved target</span>
                  <strong>{result.resolved_target?.name ?? 'Not resolved'}</strong>
                  <small>
                    {result.resolved_target
                      ? `${result.resolved_target.center.x.toFixed(1)}, ${result.resolved_target.center.y.toFixed(1)} · ${result.resolved_target.source}`
                      : 'No trusted coordinate'}
                  </small>
                </div>
                <div>
                  <span>Resolved action</span>
                  <strong>{result.resolved_action?.type ?? 'No action'}</strong>
                  <small>
                    {result.resolved_action
                      ? JSON.stringify(result.resolved_action.parameters)
                      : 'Nothing can reach Robot Control'}
                  </small>
                </div>
              </div>

              <div className="model-gates">
                <header>
                  <span>Decision gates</span>
                  <small>
                    threshold {(model.status?.confidence_threshold ?? 0.8).toFixed(2)}
                  </small>
                </header>
                {gates.map((gate, index) => (
                  <div className={gateClass(gate.value.passed)} key={gate.label}>
                    <i>
                      {gate.value.passed === true
                        ? '✓'
                        : gate.value.passed === false
                          ? '×'
                          : '–'}
                    </i>
                    <span>
                      <strong>{gate.label}</strong>
                      <small>{gate.value.reason}</small>
                    </span>
                    {index < gates.length - 1 && <b aria-hidden="true" />}
                  </div>
                ))}
              </div>

              <div
                className={
                  result.execution.allowed
                    ? 'model-execution is-allowed'
                    : 'model-execution is-blocked'
                }
              >
                <span>
                  {result.execution.allowed ? 'Action eligible' : 'Action blocked'}
                </span>
                <strong>Executed: NO</strong>
                <p>{result.execution.reason}</p>
              </div>
            </section>
          </div>

          <LazyJsonDetails
            className="model-raw-response"
            title="Raw model response"
            hint="Expand JSON trace"
            value={result.raw_response}
          />
        </>
      ) : (
        <div className="model-empty">
          <EmptyState
            title="No model replay yet"
            description="Choose the live frame or a saved frame, then run the model-only debug boundary."
          />
        </div>
      )}
    </Panel>
  )
}
