export type RobotMode = 'MOCK' | 'REAL' | 'DRY-RUN'
export type PenState = 'up' | 'down' | 'unknown'

export interface RobotCoordinates {
  x: number
  y: number
}

export interface WorkspaceBounds {
  min_x: number
  max_x: number
  min_y: number
  max_y: number
}

export interface RobotStatus {
  connected: boolean
  busy: boolean
  homed: boolean
  mode: RobotMode
  position: RobotCoordinates
  pen: PenState
  last_command: string | null
  workspace: WorkspaceBounds
  queue_depth: number
}

export interface RobotCommandResponse {
  ok: true
  action: string
}

export type RobotCommandName =
  'Move' | 'Tap' | 'Home' | 'Pen up' | 'Pen down' | 'Emergency stop'

export interface RobotCommandResult {
  name: RobotCommandName
  succeeded: boolean
  latencyMs: number
  completedAt: Date
}
