import { FocusedCameraPanel } from '../features/debug/FocusedCameraPanel'
import { FocusedVisionPanel } from '../features/debug/FocusedVisionPanel'
import { useCameraStream } from '../features/camera/useCameraStream'
import { useVisionDebug } from '../features/vision/useVisionDebug'

export function DebugPage() {
  const camera = useCameraStream()
  const vision = useVisionDebug()

  return (
    <div className="vision-workspace-page">
      <FocusedCameraPanel camera={camera} vision={vision} />
      <FocusedVisionPanel
        vision={vision}
        canSaveFrame={camera.frame !== null && camera.isConnected}
      />
    </div>
  )
}
