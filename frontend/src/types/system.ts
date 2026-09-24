import type { RobotMode, RobotStatus, WorkspaceBounds } from './robot'
import type { ModelStatus } from './model'

export interface BackendSystemStatus {
  robot: string
  robot_connected: boolean
  robot_mode: RobotMode
  robot_busy: boolean
  robot_queue_depth: number
  camera_opened: boolean
  camera_error: string | null
  camera_frame_id: number | null
  workspace: WorkspaceBounds
  calibration_profile: string | null
  model_provider: string
  model_name: string
  model_connected: boolean
  model_latency_ms: number | null
  vision_detectors: string[]
}

export type BackendConnectionState = 'connecting' | 'online' | 'offline'

export interface SystemStatusContextValue {
  backend: BackendSystemStatus | null
  backendState: BackendConnectionState
  backendError: string | null
  robotStatus: RobotStatus | null
  robotError: string | null
  modelStatus: ModelStatus | null
  modelError: string | null
  cameraError: string | null
  calibrationMissing: boolean
  isEmergencyStopping: boolean
  emergencyError: string | null
  refresh: () => void
  emergencyStop: () => void
}
