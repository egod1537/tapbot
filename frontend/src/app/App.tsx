import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from '../components/AppShell'
import { DebugPage } from '../pages/DebugPage'
import { SettingsPage } from '../pages/SettingsPage'
import { SimulationToolPage } from '../pages/SimulationToolPage'
import { WebcamToolPage } from '../pages/WebcamToolPage'
import { SystemStatusProvider } from './SystemStatusContext'

export function App() {
  return (
    <SystemStatusProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/debug" replace />} />
          <Route path="debug" element={<DebugPage />} />
          <Route path="tools/webcam" element={<WebcamToolPage />} />
          <Route path="tools/simulation" element={<SimulationToolPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/debug" replace />} />
        </Route>
      </Routes>
    </SystemStatusProvider>
  )
}
