import { useCameraStream } from '../features/camera/useCameraStream'
import { RawCanonicalWorkspace } from '../features/debug/RawCanonicalWorkspace'
import { useRawCanonicalView } from '../features/vision/useRawCanonicalView'

export function DebugPage() {
  const camera = useCameraStream()
  const workspace = useRawCanonicalView(camera)

  return (
    <div className="vision-workspace-page">
      <RawCanonicalWorkspace camera={camera} workspace={workspace} />
    </div>
  )
}
