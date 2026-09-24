export interface VisionDetectorCapability {
  type: string
  name: string
}

export interface VisionCapabilities {
  detectors: VisionDetectorCapability[]
  max_saved_frames: number
}

export interface VisionFrameMetadata {
  frame_id: number
  captured_at: string
  width: number
  height: number
  source_id: string | null
  already_canonical: boolean
}

export interface VisionFramesResponse {
  frames: VisionFrameMetadata[]
}

export interface SavedVisionFrameResponse {
  frame: VisionFrameMetadata
}

export interface VisionBoundingBox {
  x: number
  y: number
  width: number
  height: number
}

export interface VisionPoint {
  x: number
  y: number
}

export interface VisionDetection {
  id: string
  label: string
  bbox: VisionBoundingBox
  center: VisionPoint
  confidence: number
  detector_type: string
  detector_name: string
}

export interface VisionRunPayload {
  frame_id: number
  detector_types?: string[]
  confidence_threshold: number
}

export interface VisionRunResult {
  result_id: number
  frame: VisionFrameMetadata
  rectified: {
    width: number
    height: number
  }
  detector_types: string[]
  confidence_threshold: number
  detections: VisionDetection[]
  phone_screen: PhoneScreenDetection | null
}

export interface PhoneScreenCorners {
  tl: VisionPoint
  tr: VisionPoint
  br: VisionPoint
  bl: VisionPoint
}

export interface PhoneScreenOverlay {
  polygon: VisionPoint[]
  corners: Array<VisionPoint & { label: 'TL' | 'TR' | 'BR' | 'BL' }>
  center: VisionPoint
  label: string
}

export interface PhoneScreenDetection {
  found: boolean
  confidence: number
  corners: PhoneScreenCorners | null
  bbox: VisionBoundingBox | null
  center: VisionPoint | null
  source: 'contour' | 'calibration' | 'already_canonical' | null
  failure_reason: string | null
  debug_metadata: Record<string, unknown>
}

export interface PhoneScreenRunPayload {
  frame_id?: number
  canonical_width?: number
  canonical_height?: number
  use_calibration_fallback?: boolean
}

export interface PhoneScreenRunResult extends PhoneScreenDetection {
  frame_id: number
  frame: VisionFrameMetadata
  phone_detection_result_id: number
  canonical_result_id: number | null
  result_id: number | null
  canonical: { width: number; height: number } | null
  overlay: PhoneScreenOverlay | null
}

export interface ScreenPipelineRunPayload {
  frame_id?: number
  detector_types?: string[]
  confidence_threshold: number
  canonical_width?: number
  canonical_height?: number
  use_calibration_fallback?: boolean
}

export interface ScreenPipelineTimings {
  phone_detection_ms: number
  canonical_transform_ms: number
  ui_detection_ms: number
  total_ms: number
}

export interface ScreenPipelinePhoneDetection extends PhoneScreenDetection {
  result_id: number
}

export interface ScreenPipelineCanonical {
  result_id: number
  width: number
  height: number
  transform_skipped: boolean
}

export type ScreenPipelineFailureStage =
  'phone_detection' | 'canonical_transform' | 'ui_detection' | 'pipeline_setup'

export interface ScreenPipelineRunResult {
  frame_id: number
  frame: VisionFrameMetadata
  phone_detection: ScreenPipelinePhoneDetection
  canonical: ScreenPipelineCanonical | null
  detections: VisionDetection[]
  detector_types: string[]
  confidence_threshold: number
  timings: ScreenPipelineTimings
  already_canonical: boolean
  failure_stage: ScreenPipelineFailureStage | null
  error: string | null
}
