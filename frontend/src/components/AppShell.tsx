import { Outlet } from 'react-router-dom'
import { Header } from './Header'
import { SystemSafetyBar } from './SystemSafetyBar'

export function AppShell() {
  return (
    <div className="app-shell">
      <Header />
      <SystemSafetyBar />
      <main className="route-content">
        <Outlet />
      </main>
    </div>
  )
}
