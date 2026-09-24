import { useEffect, useMemo, useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { Panel } from '../../components/Panel'
import { CameraIcon } from '../../components/icons'
import type { MockGraphHotspot } from '../../types/camera'
import type { MockGraphDebugStatus } from '../../types/mock-graph'
import type { CameraStreamController } from '../camera/useCameraStream'
import { mockGraphApi } from './mock-graph-api'

const STATUS_INTERVAL_MS = 750

interface MockGraphDebugPanelProps {
  camera: CameraStreamController
}

interface Notice {
  tone: 'success' | 'warning' | 'error'
  text: string
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Mock graph request failed.'
}

function hotspotCenter(hotspot: MockGraphHotspot): { x: number; y: number } {
  return {
    x: hotspot.x + hotspot.width / 2,
    y: hotspot.y + hotspot.height / 2,
  }
}

export function MockGraphDebugPanel({ camera }: MockGraphDebugPanelProps) {
  const [status, setStatus] = useState<MockGraphDebugStatus | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busyAction, setBusyAction] = useState<'transition' | 'reset' | 'tap' | null>(
    null,
  )
  const [manualState, setManualState] = useState('')
  const [tapX, setTapX] = useState('0')
  const [tapY, setTapY] = useState('0')
  const [hoveredHotspot, setHoveredHotspot] = useState<string | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)

  useEffect(() => {
    let active = true
    let timer: number | undefined
    let controller: AbortController | undefined

    const poll = async () => {
      controller = new AbortController()
      try {
        const nextStatus = await mockGraphApi.status(controller.signal)
        if (active) {
          setStatus(nextStatus)
          setLoadError(null)
        }
      } catch (error) {
        if (active && !controller.signal.aborted) {
          setStatus(null)
          setLoadError(errorMessage(error))
        }
      } finally {
        if (active) {
          timer = window.setTimeout(() => void poll(), STATUS_INTERVAL_MS)
        }
      }
    }

    void poll()
    return () => {
      active = false
      controller?.abort()
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [])

  const currentNode = useMemo(
    () => status?.states.find((state) => state.id === status.current_state) ?? null,
    [status],
  )
  const transitionTarget =
    status?.states.some((state) => state.id === manualState) === true
      ? manualState
      : (status?.current_state ?? '')

  const setTapFromHotspot = (hotspot: MockGraphHotspot) => {
    const point = hotspotCenter(hotspot)
    setTapX(point.x.toString())
    setTapY(point.y.toString())
  }

  const manualTransition = async () => {
    if (!transitionTarget) return
    setBusyAction('transition')
    setNotice(null)
    try {
      const result = await mockGraphApi.transition(transitionTarget)
      setStatus(result.status)
      camera.invalidateFrame()
      setNotice({
        tone: 'success',
        text: `${result.transition.from_state} → ${result.transition.to_state}`,
      })
    } catch (error) {
      setNotice({ tone: 'error', text: errorMessage(error) })
    } finally {
      setBusyAction(null)
    }
  }

  const reset = async () => {
    setBusyAction('reset')
    setNotice(null)
    try {
      const result = await mockGraphApi.reset()
      setStatus(result.status)
      camera.invalidateFrame()
      setNotice({ tone: 'success', text: `Reset to ${result.status.current_state}` })
    } catch (error) {
      setNotice({ tone: 'error', text: errorMessage(error) })
    } finally {
      setBusyAction(null)
    }
  }

  const simulateTap = async () => {
    const x = Number(tapX)
    const y = Number(tapY)
    if (!tapX.trim() || !tapY.trim() || !Number.isFinite(x) || !Number.isFinite(y)) {
      setNotice({ tone: 'error', text: 'Tap X and Y must be finite numbers.' })
      return
    }

    setBusyAction('tap')
    setNotice(null)
    try {
      const result = await mockGraphApi.tap(x, y)
      setStatus(result.status)
      if (result.hit) camera.invalidateFrame()
      setNotice(
        result.hit
          ? {
              tone: 'success',
              text: `HIT ${result.tap.hotspot_id ?? ''} → ${result.status.current_state}`,
            }
          : {
              tone: 'warning',
              text: `MISS at (${x.toString()}, ${y.toString()}) · state unchanged`,
            },
      )
    } catch (error) {
      setNotice({ tone: 'error', text: errorMessage(error) })
    } finally {
      setBusyAction(null)
    }
  }

  return (
    <Panel
      title="Mock Graph Debug"
      eyebrow="Simulation / State graph"
      className="mock-graph-panel"
      actions={
        <span className={status ? 'mock-graph-source is-active' : 'mock-graph-source'}>
          {status?.source_id ?? 'No mock source'}
        </span>
      }
    >
      {!status ? (
        <EmptyState
          icon={<CameraIcon />}
          title="Mock graph is unavailable"
          description={
            loadError ?? 'Select a Mock camera source from Camera Preview first.'
          }
        />
      ) : (
        <>
          <div className="mock-graph-summary">
            <div>
              <span>Current State</span>
              <strong>{status.current_state}</strong>
            </div>
            <div>
              <span>Previous State</span>
              <strong>{status.previous_state ?? '—'}</strong>
            </div>
            <div>
              <span>Last Transition</span>
              <strong>
                {status.last_transition
                  ? `${status.last_transition.from_state} → ${status.last_transition.to_state}`
                  : '—'}
              </strong>
              <small>{status.last_transition?.trigger ?? 'No transition yet'}</small>
            </div>
            <div>
              <span>Current Image</span>
              <strong>{currentNode?.image ?? '—'}</strong>
            </div>
          </div>

          <div className="mock-graph-controls">
            <label>
              <span>Manual Transition</span>
              <select
                value={transitionTarget}
                disabled={busyAction !== null}
                onChange={(event) => setManualState(event.target.value)}
              >
                {status.states.map((state) => (
                  <option key={state.id} value={state.id}>
                    {state.id}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              disabled={busyAction !== null || !transitionTarget}
              onClick={() => void manualTransition()}
            >
              {busyAction === 'transition' ? 'Transitioning…' : 'Transition'}
            </button>
            <label>
              <span>Tap X</span>
              <input
                inputMode="decimal"
                value={tapX}
                disabled={busyAction !== null}
                onChange={(event) => setTapX(event.target.value)}
              />
            </label>
            <label>
              <span>Tap Y</span>
              <input
                inputMode="decimal"
                value={tapY}
                disabled={busyAction !== null}
                onChange={(event) => setTapY(event.target.value)}
              />
            </label>
            <button
              type="button"
              disabled={busyAction !== null}
              onClick={() => void simulateTap()}
            >
              {busyAction === 'tap' ? 'Simulating…' : 'Simulate Tap'}
            </button>
            <button
              type="button"
              className="mock-graph-reset"
              disabled={busyAction !== null}
              onClick={() => void reset()}
            >
              {busyAction === 'reset' ? 'Resetting…' : 'Reset'}
            </button>
          </div>

          {notice && (
            <p className={`mock-graph-notice is-${notice.tone}`} role="status">
              {notice.text}
            </p>
          )}

          <div className="mock-graph-workspace">
            <div className="mock-graph-preview">
              {camera.frame ? (
                <>
                  <img
                    src={camera.frame.objectUrl}
                    alt={`Mock graph state ${status.current_state}`}
                  />
                  <svg
                    viewBox={`0 0 ${camera.frame.width.toString()} ${camera.frame.height.toString()}`}
                    preserveAspectRatio="xMidYMid meet"
                    aria-label={`${status.available_hotspots.length.toString()} hotspot overlays`}
                  >
                    {status.available_hotspots.map((hotspot) => {
                      const active = hoveredHotspot === hotspot.id
                      return (
                        <g
                          key={hotspot.id}
                          className={
                            active ? 'mock-hotspot is-highlighted' : 'mock-hotspot'
                          }
                          onMouseEnter={() => setHoveredHotspot(hotspot.id)}
                          onMouseLeave={() => setHoveredHotspot(null)}
                          onClick={() => setTapFromHotspot(hotspot)}
                        >
                          <rect
                            x={hotspot.x}
                            y={hotspot.y}
                            width={hotspot.width}
                            height={hotspot.height}
                          />
                          <text x={hotspot.x + 8} y={hotspot.y + 22}>
                            {hotspot.label} → {hotspot.next_state}
                          </text>
                        </g>
                      )
                    })}
                  </svg>
                </>
              ) : (
                <EmptyState
                  icon={<CameraIcon />}
                  title="Waiting for mock frame"
                  description={camera.error ?? 'The next graph frame is loading.'}
                />
              )}
            </div>

            <aside className="mock-hotspot-list">
              <header>
                <span>Current Hotspots</span>
                <strong>{status.available_hotspots.length}</strong>
              </header>
              {status.available_hotspots.length === 0 ? (
                <p>No outgoing hotspots in this state.</p>
              ) : (
                status.available_hotspots.map((hotspot) => (
                  <button
                    type="button"
                    key={hotspot.id}
                    className={
                      hoveredHotspot === hotspot.id ? 'is-highlighted' : undefined
                    }
                    onMouseEnter={() => setHoveredHotspot(hotspot.id)}
                    onMouseLeave={() => setHoveredHotspot(null)}
                    onFocus={() => setHoveredHotspot(hotspot.id)}
                    onBlur={() => setHoveredHotspot(null)}
                    onClick={() => setTapFromHotspot(hotspot)}
                  >
                    <strong>{hotspot.label}</strong>
                    <span>{hotspot.id}</span>
                    <small>
                      [{hotspot.x}, {hotspot.y}, {hotspot.width}, {hotspot.height}]
                    </small>
                    <em>→ {hotspot.next_state}</em>
                  </button>
                ))
              )}
            </aside>
          </div>

          <div className="mock-graph-overview">
            <section>
              <header>
                <h3>Nodes</h3>
                <span>{status.states.length}</span>
              </header>
              <div className="mock-node-list">
                {status.states.map((state) => (
                  <button
                    type="button"
                    key={state.id}
                    className={
                      state.id === status.current_state ? 'is-current' : undefined
                    }
                    onClick={() => setManualState(state.id)}
                  >
                    <strong>{state.id}</strong>
                    <span>{state.image}</span>
                    <small>{state.hotspots.length} hotspots</small>
                  </button>
                ))}
              </div>
            </section>
            <section>
              <header>
                <h3>Edges</h3>
                <span>{status.edges.length}</span>
              </header>
              <div className="mock-edge-list">
                {status.edges.map((edge) => (
                  <div key={edge.id}>
                    <strong>{edge.from_state}</strong>
                    <span>→</span>
                    <strong>{edge.to_state}</strong>
                    <small>{edge.label}</small>
                  </div>
                ))}
              </div>
            </section>
          </div>
        </>
      )}
    </Panel>
  )
}
