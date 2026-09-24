import { useSystemStatus } from '../app/system-status'

export function SystemSafetyBar() {
  const system = useSystemStatus()
  const mode = system.backend?.robot_mode ?? system.robotStatus?.mode ?? 'OFFLINE'
  const issues = [
    system.backendState === 'offline'
      ? { kind: 'backend', label: 'Backend disconnected', detail: system.backendError }
      : null,
    system.cameraError
      ? { kind: 'camera', label: 'Camera unavailable', detail: system.cameraError }
      : null,
    system.robotError
      ? { kind: 'robot', label: 'Robot unavailable', detail: system.robotError }
      : null,
    system.modelError
      ? { kind: 'model', label: 'Model unavailable', detail: system.modelError }
      : null,
    system.calibrationMissing
      ? {
          kind: 'calibration',
          label: 'Calibration missing',
          detail: 'Vision and model transforms are blocked.',
        }
      : null,
    system.emergencyError
      ? {
          kind: 'emergency',
          label: 'Emergency stop failed',
          detail: system.emergencyError,
        }
      : null,
  ].filter((issue): issue is NonNullable<typeof issue> => issue !== null)

  return (
    <div className={`system-safety-bar is-${mode.toLowerCase()}`}>
      <div className="system-mode-indicator">
        <span>Robot mode</span>
        <strong>{mode}</strong>
        {mode === 'REAL' && <em>Physical motion enabled</em>}
      </div>
      <div className="system-issues" aria-live="polite">
        {issues.length === 0 ? (
          <span className="system-nominal">
            Pipeline status nominal
            {system.backend?.calibration_profile && (
              <small>Calibration: {system.backend.calibration_profile}</small>
            )}
          </span>
        ) : (
          issues.map((issue) => (
            <span
              className={`system-issue is-${issue.kind}`}
              title={issue.detail ?? ''}
              key={issue.kind}
            >
              <i aria-hidden="true" />
              <strong>{issue.label}</strong>
              <small>{issue.detail}</small>
            </span>
          ))
        )}
      </div>
      <div className="system-safety-actions">
        <button type="button" onClick={system.refresh}>
          Refresh status
        </button>
        <button
          type="button"
          className="system-emergency-stop"
          disabled={system.isEmergencyStopping}
          onClick={system.emergencyStop}
        >
          {system.isEmergencyStopping ? 'Stopping…' : 'Emergency stop'}
        </button>
      </div>
    </div>
  )
}
