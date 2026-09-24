import { useSystemStatus } from '../app/system-status'
import { CameraWorkspace } from '../features/debug/CameraWorkspace'
import { DeveloperToolsDrawer } from '../features/debug/DeveloperToolsDrawer'
import { ModelDebugPanel } from '../features/debug/ModelDebugPanel'
import { RobotControlPanel } from '../features/debug/RobotControlPanel'
import { TimelinePanel } from '../features/debug/TimelinePanel'
import { VisionPreviewPanel } from '../features/debug/VisionPreviewPanel'

export function DebugPage() {
  const system = useSystemStatus()
  const mode = system.backend?.robot_mode ?? system.robotStatus?.mode ?? 'OFFLINE'

  return (
    <div className="dashboard-page">
      <div className="dashboard-intro">
        <div>
          <p className="eyebrow">Development workspace</p>
          <h1>Debug Dashboard</h1>
        </div>
        <p>
          <span className={`mock-label dashboard-mode is-${mode.toLowerCase()}`}>
            {mode}
          </span>
          Live pipeline workspace
        </p>
      </div>

      <div className="integrated-dashboard">
        <div className="dashboard-primary">
          <CameraWorkspace />
          <RobotControlPanel />
        </div>
        <div className="dashboard-secondary">
          <VisionPreviewPanel />
          <ModelDebugPanel />
        </div>
        <TimelinePanel />
        <DeveloperToolsDrawer />
      </div>
    </div>
  )
}
