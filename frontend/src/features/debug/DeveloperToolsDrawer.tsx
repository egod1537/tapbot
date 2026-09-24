import { useState } from 'react'
import { CalibrationPanel } from '../calibration/CalibrationPanel'
import { useCameraStream } from '../camera/useCameraStream'
import { GcodeConsolePanel } from '../gcode/GcodeConsolePanel'
import { MockGraphDebugPanel } from '../mock-graph/MockGraphDebugPanel'

type DeveloperTool = 'calibration' | 'mock-graph' | 'gcode'

function CalibrationTool() {
  const camera = useCameraStream()
  return <CalibrationPanel camera={camera} />
}

function MockGraphTool() {
  const camera = useCameraStream()
  return <MockGraphDebugPanel camera={camera} />
}

function ActiveTool({ tool }: { tool: DeveloperTool }) {
  if (tool === 'calibration') return <CalibrationTool />
  if (tool === 'mock-graph') return <MockGraphTool />
  return <GcodeConsolePanel />
}

export function DeveloperToolsDrawer() {
  const [activeTool, setActiveTool] = useState<DeveloperTool | null>(null)

  const toggleTool = (tool: DeveloperTool) => {
    setActiveTool((current) => (current === tool ? null : tool))
  }

  return (
    <section className={activeTool ? 'developer-drawer is-open' : 'developer-drawer'}>
      <header>
        <div>
          <p className="eyebrow">Isolated developer tools</p>
          <h2>Calibration / Simulation / Low-level Console</h2>
        </div>
        <div className="developer-tabs" role="tablist" aria-label="Developer tools">
          <button
            type="button"
            role="tab"
            aria-selected={activeTool === 'mock-graph'}
            className={activeTool === 'mock-graph' ? 'is-active' : undefined}
            onClick={() => toggleTool('mock-graph')}
          >
            Mock Graph
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTool === 'calibration'}
            className={activeTool === 'calibration' ? 'is-active' : undefined}
            onClick={() => toggleTool('calibration')}
          >
            Calibration
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTool === 'gcode'}
            className={
              activeTool === 'gcode' ? 'is-active is-dangerous' : 'is-dangerous'
            }
            onClick={() => toggleTool('gcode')}
          >
            G-code Console
          </button>
          {activeTool && (
            <button
              type="button"
              className="developer-drawer__close"
              aria-label="Close developer tools"
              onClick={() => setActiveTool(null)}
            >
              ×
            </button>
          )}
        </div>
      </header>
      {activeTool && (
        <div className="developer-drawer__content" role="tabpanel">
          <ActiveTool tool={activeTool} />
        </div>
      )}
    </section>
  )
}
