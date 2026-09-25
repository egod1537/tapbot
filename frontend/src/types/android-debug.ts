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
  device_id: string
  name: string
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
  device_id: string
  source_id: string
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
  ui_tree?: {
    available: boolean
    captured_at: string | null
    package_name: string | null
    node_count: number
    truncated: boolean
    error: string | null
  }
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
  device_id: string
  frame: AndroidFrameMetadata
  path: string
}

export interface AndroidPrimitiveResult {
  ok: true
  device_id: string
  result: Record<string, unknown>
}

export interface AndroidPointerPoint {
  x: number
  y: number
  t_ms: number
}

export interface AndroidUiBounds {
  left: number
  top: number
  right: number
  bottom: number
}

export interface AndroidUiNode {
  node_id: string
  parent_id: string | null
  depth: number
  class_name: string | null
  text: string | null
  content_description: string | null
  view_id_resource_name: string | null
  package_name: string | null
  bounds: AndroidUiBounds
  clickable: boolean
  enabled: boolean
  focusable: boolean
  focused: boolean
  selected: boolean
  checked: boolean
  checkable: boolean
  scrollable: boolean
  editable: boolean
  visible_to_user: boolean
  password: boolean
  child_count: number
  children?: AndroidUiNode[]
}

export interface AndroidUiTree {
  ok: true
  request_id: string
  device_id: string
  source_id: string
  captured_at: string
  package_name: string | null
  window_title: string | null
  rotation: number
  screen_width: number
  screen_height: number
  node_count: number
  truncated: boolean
  root: AndroidUiNode
  nodes: AndroidUiNode[]
}

export interface AndroidDeviceSummary {
  id: string
  name: string
  connected: boolean
  last_seen_at: string | null
  capture_ready: boolean
  stream_running: boolean
  accessibility_enabled: boolean
  remote_control_enabled: boolean
  macro_status: MacroStatus
  last_error: string | null
}

export interface AndroidDevicesResponse {
  devices: AndroidDeviceSummary[]
  default_device_id: string | null
}
