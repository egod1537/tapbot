import type {
  CameraSourceMetadata,
  MockGraphStatus,
  MockGraphTap,
  MockGraphTransition,
} from './camera'

export interface MockGraphDebugStatus extends MockGraphStatus {
  source_id: string
  name: string
  metadata: CameraSourceMetadata
}

export interface MockGraphActionResponse {
  transition: MockGraphTransition
  status: MockGraphDebugStatus
}

export interface MockGraphTapResponse {
  hit: boolean
  tap: MockGraphTap
  transition: MockGraphTransition | null
  status: MockGraphDebugStatus
}
