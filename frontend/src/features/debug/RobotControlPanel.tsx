import { useMemo, useState } from 'react'
import { KeyValueRow } from '../../components/KeyValueRow'
import { Panel } from '../../components/Panel'
import { Toast } from '../../components/Toast'
import type { WorkspaceBounds } from '../../types/robot'
import { useRobotControl } from '../robot/useRobotControl'

const FALLBACK_BOUNDS: WorkspaceBounds = {
  min_x: 0,
  max_x: 300,
  min_y: 0,
  max_y: 300,
}

function coordinateValue(value: string): number | null {
  if (value.trim() === '') return null
  const number = Number(value)
  return Number.isFinite(number) ? number : null
}

function coordinateError(
  axis: 'X' | 'Y',
  value: number | null,
  min: number,
  max: number,
): string | null {
  if (value === null) return `${axis} must be a number.`
  if (value < min || value > max) {
    return `${axis} must be between ${min} and ${max} mm.`
  }
  return null
}

function preventNonNumericKeys(event: React.KeyboardEvent<HTMLInputElement>) {
  if (['e', 'E', '+'].includes(event.key)) event.preventDefault()
}

export function RobotControlPanel() {
  const robot = useRobotControl()
  const [xInput, setXInput] = useState('0')
  const [yInput, setYInput] = useState('0')
  const bounds = robot.status?.workspace ?? FALLBACK_BOUNDS
  const x = coordinateValue(xInput)
  const y = coordinateValue(yInput)
  const xError = coordinateError('X', x, bounds.min_x, bounds.max_x)
  const yError = coordinateError('Y', y, bounds.min_y, bounds.max_y)
  const inputError = xError ?? yError
  const isBusy = robot.pendingCommand !== null || robot.status?.busy === true
  const isConnected = robot.status?.connected === true
  const motionDisabled = inputError !== null || isBusy || !isConnected
  const commandDisabled = isBusy || !isConnected

  const coordinates = useMemo(
    () => ({ x: x ?? bounds.min_x, y: y ?? bounds.min_y }),
    [bounds.min_x, bounds.min_y, x, y],
  )

  return (
    <>
      <Panel
        title="Robot Control"
        eyebrow="Manual control / 02"
        className="robot-panel"
        actions={
          <span
            className={`mode-chip mode-chip--${robot.status?.mode.toLowerCase() ?? 'offline'}`}
          >
            {robot.status?.mode ?? 'Offline'}
          </span>
        }
      >
        {robot.status?.mode === 'DRY-RUN' && (
          <div className="dry-run-banner">
            Dry run enabled — commands are recorded but hardware will not move.
          </div>
        )}

        <div className="robot-state-grid">
          <div>
            <span>Current X</span>
            <strong>{robot.status?.position.x.toFixed(1) ?? '—'}</strong>
            <small>mm</small>
          </div>
          <div>
            <span>Current Y</span>
            <strong>{robot.status?.position.y.toFixed(1) ?? '—'}</strong>
            <small>mm</small>
          </div>
          <div>
            <span>Homed</span>
            <strong>{robot.status ? (robot.status.homed ? 'YES' : 'NO') : '—'}</strong>
          </div>
          <div>
            <span>Connection</span>
            <strong className={isConnected ? 'state-ok' : 'state-error'}>
              {isConnected ? 'ONLINE' : 'OFFLINE'}
            </strong>
          </div>
        </div>

        {robot.statusError && (
          <div className="robot-error" role="alert">
            <span>Robot unavailable: {robot.statusError}</span>
            <button type="button" onClick={robot.refreshStatus}>
              Retry
            </button>
          </div>
        )}

        <div className="coordinate-inputs">
          <label>
            <span>X position</span>
            <span className="number-input">
              <input
                type="number"
                inputMode="decimal"
                min={bounds.min_x}
                max={bounds.max_x}
                step="any"
                value={xInput}
                aria-invalid={xError !== null}
                onKeyDown={preventNonNumericKeys}
                onChange={(event) => setXInput(event.target.value)}
              />
              <span>mm</span>
            </span>
            <small>
              {bounds.min_x} – {bounds.max_x} mm
            </small>
          </label>
          <label>
            <span>Y position</span>
            <span className="number-input">
              <input
                type="number"
                inputMode="decimal"
                min={bounds.min_y}
                max={bounds.max_y}
                step="any"
                value={yInput}
                aria-invalid={yError !== null}
                onKeyDown={preventNonNumericKeys}
                onChange={(event) => setYInput(event.target.value)}
              />
              <span>mm</span>
            </span>
            <small>
              {bounds.min_y} – {bounds.max_y} mm
            </small>
          </label>
        </div>
        <div
          className={
            inputError ? 'coordinate-validation is-invalid' : 'coordinate-validation'
          }
          aria-live="polite"
        >
          {inputError ?? 'Coordinates are inside the configured workspace.'}
        </div>

        <div className="motion-actions">
          <button
            type="button"
            className="button button--primary"
            disabled={motionDisabled}
            onClick={() => robot.move(coordinates)}
          >
            {robot.pendingCommand === 'Move' ? 'Moving…' : 'Move'}
          </button>
          <button
            type="button"
            className="button"
            disabled={motionDisabled}
            onClick={() => robot.tap(coordinates)}
          >
            {robot.pendingCommand === 'Tap' ? 'Tapping…' : 'Tap'}
          </button>
          <button
            type="button"
            className="button"
            disabled={commandDisabled}
            onClick={robot.home}
          >
            {robot.pendingCommand === 'Home' ? 'Homing…' : 'Home'}
          </button>
        </div>

        <div className="pen-actions">
          <span>Pen</span>
          <button
            type="button"
            className={robot.status?.pen === 'up' ? 'button is-selected' : 'button'}
            disabled={commandDisabled}
            onClick={robot.penUp}
          >
            Pen up
          </button>
          <button
            type="button"
            className={robot.status?.pen === 'down' ? 'button is-selected' : 'button'}
            disabled={commandDisabled}
            onClick={robot.penDown}
          >
            Pen down
          </button>
        </div>

        <button
          type="button"
          className="emergency-stop"
          disabled={robot.isStopping}
          onClick={robot.emergencyStop}
        >
          <span className="emergency-stop__icon" aria-hidden="true">
            !
          </span>
          <span>
            <strong>{robot.isStopping ? 'Stopping…' : 'Emergency stop'}</strong>
            <small>Immediate · no confirmation</small>
          </span>
        </button>

        <dl className="command-result">
          <KeyValueRow
            label="Controller"
            value={isBusy ? `BUSY · ${robot.pendingCommand ?? 'Queued'}` : 'IDLE'}
            accent={!isBusy && isConnected}
          />
          <KeyValueRow
            label="Last command"
            value={robot.lastResult?.name ?? robot.status?.last_command ?? '—'}
          />
          <KeyValueRow
            label="Latency"
            value={
              robot.lastResult ? `${robot.lastResult.latencyMs.toString()} ms` : '—'
            }
          />
        </dl>
      </Panel>
      <Toast toast={robot.toast} onDismiss={robot.dismissToast} />
    </>
  )
}
