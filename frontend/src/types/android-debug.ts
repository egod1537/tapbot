import type { VisionDetection } from './vision'

export type MacroStatus = 'IDLE' | 'RUNNING' | 'PAUSED' | 'STOPPED' | 'STEPPING'

export interface AndroidDeviceStatus {
  width: number
  height: number
  rotation: number
  density: number
  manufacturer?: string
  model?: string
  android_version?: string
}

export interface AndroidDisplayStatus {
  logical_width: number
  logical_height: number
  rotation: number
  insets?: { top: number; bottom: number; left: number; right: number }
}

export interface AndroidAgentStatus {
  accessibility_enabled: boolean
  capture_ready: boolean
  stream_running: boolean
  remote_control_enabled: boolean
  agent_version: string
  device: AndroidDeviceStatus
  display?: AndroidDisplayStatus
}

export interface AndroidStreamStatus {
  running: boolean
  codec: string
  transport: string
  width: number
  height: number
  rotation: number
  fps: number
  target_fps: number
  bitrate: number
  clients: number
  capture_latency_ms: number | null
  encode_latency_ms: number | null
  frame_age_ms: number | null
}

export interface AndroidProxyStatus {
  configured: boolean
  connected: boolean
  error: string | null
  agent: AndroidAgentStatus | null
  stream: AndroidStreamStatus | null
  macro_status: MacroStatus
}

export interface AndroidFrameMetadata {
  frame_id: string
  source_id: string
  captured_at: string
  width: number
  height: number
  rotation: number
  already_canonical: true
}

export interface AndroidDebugState {
  state: {
    current: string
    previous: string | null
    confidence: number
  }
  macro: {
    id: string
    status: MacroStatus
    step_index: number
  }
  frame: AndroidFrameMetadata | null
  detections: VisionDetection[]
  vision_latency_ms: number | null
  decision: {
    classifier: { state: string; confidence: number }
    vlm: Record<string, unknown> | null
    target: {
      name: string
      source: string
      screen: { x: number; y: number }
      device: { x: number; y: number }
    } | null
    final_action: Record<string, unknown> | null
    blocked_reason: string | null
  }
  last_action: Record<string, unknown> | null
  last_action_result: Record<string, unknown> | null
  error: string | null
}

export interface AndroidScreenshotSaveResult {
  ok: true
  frame: AndroidFrameMetadata
  path: string
}

export interface AndroidPrimitiveResult {
  ok: true
  result: Record<string, unknown>
}
