import { useCameraStream } from '../features/camera/useCameraStream'
import { RawCanonicalWorkspace } from '../features/debug/RawCanonicalWorkspace'
import { useRawCanonicalView } from '../features/vision/useRawCanonicalView'

export function WebcamToolPage() {
  const camera = useCameraStream()
  const workspace = useRawCanonicalView(camera)

  return (
    <div className="vision-workspace-page legacy-tool-page">
      <RawCanonicalWorkspace camera={camera} workspace={workspace} />
    </div>
  )
}
