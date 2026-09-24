import type { FramePoint } from './camera'
import type { RobotCoordinates, WorkspaceBounds } from './robot'

export type CalibrationCorners = [FramePoint, FramePoint, FramePoint, FramePoint]

export type RobotReferencePoints = [
  RobotCoordinates,
  RobotCoordinates,
  RobotCoordinates,
  RobotCoordinates,
]

export interface CalibrationPayload {
  profile_name: string
  camera_corners: CalibrationCorners
  robot_points: RobotReferencePoints
  phone_width: number
  phone_height: number
  camera_width: number
  camera_height: number
  frame_id: number
}

export interface CalibrationProfile {
  profile_name: string
  camera_corners: Array<[number, number]>
  robot_points: Array<[number, number]>
  phone_logical_size: {
    width: number
    height: number
  }
  created_at: string
  camera_resolution: [number, number] | null
  robot_work_area: WorkspaceBounds
}

export interface CalibrationResponse {
  configured: true
  calibration: CalibrationProfile
}

export interface CalibrationProfilesResponse {
  profiles: string[]
  active_profile: string | null
}

export interface CalibrationPreview {
  blob: Blob
  width: number
  height: number
  centerRobot: RobotCoordinates
}

export interface CameraTestResult {
  screen: FramePoint
  robot: RobotCoordinates
}

export interface ScreenTestResult {
  robot: RobotCoordinates
}
