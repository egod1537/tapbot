import {
  Alignment,
  Navbar,
  NavbarDivider,
  NavbarGroup,
  NavbarHeading,
  Tag,
} from '@blueprintjs/core'
import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { useSystemStatus } from '../app/system-status'
import { androidApi } from '../features/android/android-api'
import type { AndroidDeviceSummary } from '../types/android-debug'

export function Header() {
  const system = useSystemStatus()
  const location = useLocation()
  const [android, setAndroid] = useState<AndroidDeviceSummary | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    const refresh = async () => {
      try {
        const response = await androidApi.devices(controller.signal)
        const routeId = location.pathname.startsWith('/debug/android/')
          ? decodeURIComponent(location.pathname.slice('/debug/android/'.length))
          : null
        setAndroid(
          response.devices.find((device) => device.id === routeId) ??
            response.devices.find(
              (device) => device.id === response.default_device_id,
            ) ??
            response.devices.find((device) => device.connected) ??
            response.devices[0] ??
            null,
        )
      } catch {
        if (!controller.signal.aborted) setAndroid(null)
      }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 7_500)
    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [location.pathname])

  const workspace = location.pathname.startsWith('/tools/webcam')
    ? 'Legacy Webcam'
    : location.pathname.startsWith('/tools/simulation')
      ? 'Simulation'
      : 'Android Debug'

  return (
    <Navbar className="vision-navbar" fixedToTop>
      <NavbarGroup align={Alignment.LEFT}>
        <NavbarHeading className="vision-navbar__brand">TAPBOT</NavbarHeading>
        <NavbarDivider />
        <span className="vision-navbar__workspace">{workspace}</span>
        <nav className="vision-navbar__links" aria-label="Debug tools">
          <NavLink to="/debug">Android</NavLink>
          <NavLink to="/tools/webcam">Webcam</NavLink>
          <NavLink to="/tools/simulation">Simulation</NavLink>
        </nav>
      </NavbarGroup>
      <NavbarGroup align={Alignment.RIGHT} className="vision-navbar__status">
        <span>Backend</span>
        <Tag
          intent={
            system.backendState === 'online'
              ? 'success'
              : system.backendState === 'connecting'
                ? 'warning'
                : 'danger'
          }
          minimal
        >
          {system.backendState.toUpperCase()}
        </Tag>
        <span>Android</span>
        <Tag intent={android?.connected ? 'success' : 'danger'} minimal>
          {android?.connected ? 'ONLINE' : 'OFFLINE'}
        </Tag>
        <span>Stream</span>
        <Tag intent={android?.stream_running ? 'success' : 'warning'} minimal>
          {android?.stream_running ? 'LIVE' : 'OFF'}
        </Tag>
        <span>Macro</span>
        <Tag intent={android?.macro_status === 'RUNNING' ? 'success' : 'none'} minimal>
          {android?.macro_status ?? 'IDLE'}
        </Tag>
      </NavbarGroup>
    </Navbar>
  )
}
