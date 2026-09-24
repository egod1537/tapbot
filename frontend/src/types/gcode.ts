import type { RobotMode } from './robot'

export interface GcodePreset {
  command: string
  label: string
  description: string
  category: string
  dangerous: boolean
}

export interface GcodeCapabilities {
  available: boolean
  mode: RobotMode
  connected: boolean
  firmware: string | null
  max_command_length: number
  presets: GcodePreset[]
  reason: string | null
}

export interface GcodeCommandResponse {
  ok: true
  command: string
  response: string[]
  mode: RobotMode
}

export interface ConsoleEntry {
  id: number
  command: string
  response: string[]
  status: 'ok' | 'error' | 'stopped'
  timestamp: Date
  latencyMs: number
}
