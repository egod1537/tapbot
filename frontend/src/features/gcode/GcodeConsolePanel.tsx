import { useEffect, useRef } from 'react'
import type { KeyboardEvent } from 'react'
import { Panel } from '../../components/Panel'
import { useGcodeConsole } from './useGcodeConsole'

export function GcodeConsolePanel() {
  const consoleState = useGcodeConsole()
  const outputRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const isRealMode = consoleState.capabilities?.mode === 'REAL'

  useEffect(() => {
    const output = outputRef.current
    if (output) output.scrollTop = output.scrollHeight
  }, [consoleState.entries])

  const handleInputKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Enter') {
      event.preventDefault()
      consoleState.send()
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      consoleState.navigateHistory('previous')
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      consoleState.navigateHistory('next')
    }
  }

  return (
    <Panel
      title="G-code Console"
      eyebrow="Developer tools / Low-level"
      className={isRealMode ? 'gcode-panel is-real' : 'gcode-panel'}
      actions={
        <>
          <span
            className={`console-mode console-mode--${consoleState.capabilities?.mode.toLowerCase() ?? 'offline'}`}
          >
            {consoleState.capabilities?.mode ?? 'Offline'}
          </span>
          <button
            type="button"
            className="console-stop"
            disabled={consoleState.isStopping}
            onClick={consoleState.emergencyStop}
          >
            {consoleState.isStopping ? 'Stopping…' : 'Emergency stop'}
          </button>
        </>
      }
    >
      <div className="console-safety">
        <span aria-hidden="true">!</span>
        <div>
          <strong>
            {isRealMode
              ? 'REAL HARDWARE — raw commands can move the robot immediately.'
              : 'Developer console — commands bypass normal Robot Control.'}
          </strong>
          <p>
            Backend policy remains authoritative. Multi-line, unsupported, relative, and
            out-of-workspace commands are rejected.
          </p>
        </div>
      </div>

      <div className="console-layout">
        <section className="console-command-area">
          <div className="console-section-title">
            <span>Command</span>
            <span>{consoleState.capabilities?.firmware ?? 'No firmware'}</span>
          </div>

          <div className="console-input-row">
            <span aria-hidden="true">&gt;</span>
            <input
              ref={inputRef}
              type="text"
              autoComplete="off"
              autoCapitalize="characters"
              spellCheck="false"
              placeholder="Enter one backend-approved command"
              maxLength={consoleState.capabilities?.max_command_length ?? 120}
              value={consoleState.command}
              disabled={!consoleState.capabilities?.available}
              onChange={(event) => consoleState.setCommand(event.target.value)}
              onKeyDown={handleInputKeyDown}
            />
            <button
              type="button"
              disabled={
                !consoleState.command.trim() ||
                consoleState.isSending ||
                !consoleState.capabilities?.available
              }
              onClick={consoleState.send}
            >
              {consoleState.isSending ? 'Sending…' : 'Send'}
            </button>
          </div>
          <p className="console-keyboard-hint">Enter to send · ↑/↓ command history</p>

          <div className="console-section-title presets-title">
            <span>Backend capabilities</span>
            <span>{consoleState.capabilities?.presets.length ?? 0} presets</span>
          </div>
          <div className="console-presets">
            {consoleState.capabilities?.presets.map((preset) => (
              <button
                type="button"
                className={preset.dangerous ? 'is-dangerous' : undefined}
                key={preset.command}
                title={preset.description}
                onClick={() => {
                  consoleState.selectPreset(preset.command)
                  inputRef.current?.focus()
                }}
              >
                <code>{preset.command}</code>
                <span>{preset.label}</span>
              </button>
            ))}
          </div>

          {!consoleState.capabilities?.available && (
            <div className="console-unavailable" role="status">
              <span>
                {consoleState.capabilityError ??
                  consoleState.capabilities?.reason ??
                  'Loading console capabilities…'}
              </span>
              <button type="button" onClick={consoleState.refreshCapabilities}>
                Retry
              </button>
            </div>
          )}
        </section>

        <section className="console-output-area">
          <div className="console-section-title">
            <span>Transport output</span>
            <div>
              <button
                type="button"
                disabled={consoleState.entries.length === 0}
                onClick={consoleState.copyOutput}
              >
                {consoleState.copied ? 'Copied' : 'Copy'}
              </button>
              <button
                type="button"
                disabled={consoleState.entries.length === 0}
                onClick={consoleState.clear}
              >
                Clear
              </button>
            </div>
          </div>
          <div className="console-output" ref={outputRef} role="log" aria-live="polite">
            {consoleState.entries.length === 0 ? (
              <div className="console-empty">
                <span>_</span>
                Waiting for a command
              </div>
            ) : (
              consoleState.entries.map((entry) => (
                <article className={`console-entry is-${entry.status}`} key={entry.id}>
                  <header>
                    <time>{entry.timestamp.toLocaleTimeString()}</time>
                    <span>{entry.latencyMs.toString()} ms</span>
                    <strong>{entry.status}</strong>
                  </header>
                  <code className="console-entry__command">&gt; {entry.command}</code>
                  {entry.response.map((line, index) => (
                    <code key={`${entry.id.toString()}-${index.toString()}`}>
                      {entry.status === 'error' ? '! ' : '← '}
                      {line}
                    </code>
                  ))}
                </article>
              ))
            )}
          </div>
        </section>
      </div>
    </Panel>
  )
}
