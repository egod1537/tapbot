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
  detector_types: string[]
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
}
