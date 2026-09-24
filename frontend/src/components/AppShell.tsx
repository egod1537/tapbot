import { Classes } from '@blueprintjs/core'
import { Outlet } from 'react-router-dom'
import { Header } from './Header'

export function AppShell() {
  return (
    <div className={`${Classes.DARK} app-shell vision-app-shell`}>
      <Header />
      <main className="route-content">
        <Outlet />
      </main>
    </div>
  )
}
