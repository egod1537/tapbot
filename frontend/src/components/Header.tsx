import { NavLink, useLocation } from 'react-router-dom'
import { useSystemStatus } from '../app/system-status'
import { StatusBadge } from './StatusBadge'
import { GridIcon, SettingsIcon } from './icons'

export function Header() {
  const location = useLocation()
  const isDebugPage = location.pathname.startsWith('/debug')
  const system = useSystemStatus()
  const mode = system.backend?.robot_mode ?? system.robotStatus?.mode ?? 'OFFLINE'
  const cameraOnline = system.backendState === 'online' && system.cameraError === null
  const modelOnline = system.backendState === 'online' && system.modelError === null

  return (
    <header className="app-header">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <span />
        </span>
        <span className="brand-name">TAPBOT</span>
        <span className="brand-product">
          {isDebugPage ? 'Debug Dashboard' : 'Settings'}
        </span>
      </div>

      <nav className="primary-nav" aria-label="Primary navigation">
        <NavLink to="/debug">
          <GridIcon />
          Debug
        </NavLink>
        <NavLink to="/settings">
          <SettingsIcon />
          Settings
        </NavLink>
      </nav>

      <div className="header-status" aria-label="System status">
        <StatusBadge
          label="Backend"
          value={system.backendState.toUpperCase()}
          tone={
            system.backendState === 'online'
              ? 'positive'
              : system.backendState === 'connecting'
                ? 'warning'
                : 'danger'
          }
        />
        <StatusBadge
          label="Robot"
          value={mode}
          tone={mode === 'REAL' ? 'danger' : mode === 'DRY-RUN' ? 'warning' : 'neutral'}
        />
        <StatusBadge
          label="Camera"
          value={cameraOnline ? 'LIVE' : 'OFFLINE'}
          tone={cameraOnline ? 'positive' : 'danger'}
        />
        <StatusBadge
          label="Model"
          value={modelOnline ? 'READY' : 'UNAVAILABLE'}
          tone={modelOnline ? 'positive' : 'danger'}
        />
        <button
          type="button"
          className="header-emergency-stop"
          disabled={system.isEmergencyStopping}
          onClick={system.emergencyStop}
        >
          <span aria-hidden="true">!</span>
          {system.isEmergencyStopping ? 'Stopping' : 'E-stop'}
        </button>
      </div>
    </header>
  )
}
