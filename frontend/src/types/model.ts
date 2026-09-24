import type { VisionFrameMetadata } from './vision'

export interface ModelStatus {
  provider: string
  model_name: string
  connected: boolean
  last_latency_ms: number | null
  confidence_threshold: number
  execution_default: false
}

export interface StructuredDecision {
  state: string
  action: 'noop' | 'tap_target' | 'wait' | 'request_human'
  target: string | null
  confidence: number
  reason: string
}

export interface ModelGateResult {
  passed: boolean | null
  reason: string
}

export interface ModelGateResults {
  schema_valid: ModelGateResult
  confidence_threshold: ModelGateResult
  target_resolved: ModelGateResult
  action_created: ModelGateResult
}

export interface ResolvedModelTarget {
  name: string
  center: { x: number; y: number }
  source: string
}

export interface ResolvedModelAction {
  type: string
  parameters: Record<string, unknown>
}

export interface ModelRunResult {
  run_id: number
  model: ModelStatus
  frame: VisionFrameMetadata
  input: {
    image_id: string
    width: number
    height: number
  }
  context: Record<string, unknown>
  raw_response: unknown
  decision: StructuredDecision | null
  resolved_target: ResolvedModelTarget | null
  resolved_action: ResolvedModelAction | null
  gates: ModelGateResults
  execution: {
    allowed: boolean
    requested: false
    executed: false
    reason: string
  }
  status: string
  error: string | null
}

export interface ModelRunPayload {
  frame_id: number | null
  context: Record<string, unknown>
}
