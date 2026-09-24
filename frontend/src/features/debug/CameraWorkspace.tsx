import { useCameraStream } from '../camera/useCameraStream'
import { CameraPreviewPanel } from './CameraPreviewPanel'

export function CameraWorkspace() {
  const camera = useCameraStream()
  return <CameraPreviewPanel camera={camera} />
}
