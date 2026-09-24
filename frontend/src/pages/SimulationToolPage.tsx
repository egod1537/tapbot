import { Callout } from '@blueprintjs/core'
import { useCameraStream } from '../features/camera/useCameraStream'
import { MockGraphDebugPanel } from '../features/mock-graph/MockGraphDebugPanel'

export function SimulationToolPage() {
  const camera = useCameraStream()
  const isMock = camera.sourceStatus?.type === 'mock_graph'

  return (
    <div className="vision-workspace-page legacy-tool-page">
      {!isMock && camera.sourceStatus !== null && (
        <Callout intent="warning" title="Mock source required">
          Select a Mock Graph source from the legacy webcam tool before using the
          simulation inspector.
        </Callout>
      )}
      <MockGraphDebugPanel camera={camera} />
    </div>
  )
}
