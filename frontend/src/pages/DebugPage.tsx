import { AndroidDebugWorkspace } from '../features/android/AndroidDebugWorkspace'
import { useAndroidDebug } from '../features/android/useAndroidDebug'

export function DebugPage() {
  const controller = useAndroidDebug()

  return (
    <div className="vision-workspace-page">
      <AndroidDebugWorkspace controller={controller} />
    </div>
  )
}
