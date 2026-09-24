export interface FramePoint {
  x: number
  y: number
}

interface OverlayBase {
  id: string
  label?: string
  confidence?: number
  color?: string
}

export interface ScreenCornersOverlay extends OverlayBase {
  kind: 'screen-corners'
  points: [FramePoint, FramePoint, FramePoint, FramePoint]
}

export interface PolygonOverlay extends OverlayBase {
  kind: 'polygon'
  points: FramePoint[]
}

export interface BoundingBoxOverlay extends OverlayBase {
  kind: 'bbox'
  x: number
  y: number
  width: number
  height: number
}

export interface CenterPointOverlay extends OverlayBase {
  kind: 'center'
  point: FramePoint
}

export type CameraOverlayItem =
  ScreenCornersOverlay | PolygonOverlay | BoundingBoxOverlay | CenterPointOverlay

export interface CameraOverlayFrame {
  frameId?: number
  frameWidth: number
  frameHeight: number
  items: CameraOverlayItem[]
}

export interface CameraFrame {
  frameId: number
  width: number
  height: number
  capturedAt: string
  blob: Blob
  objectUrl: string
}

export type CameraSourceType = 'physical' | 'image' | 'video' | 'mock_graph'

export interface CameraSourceMetadata {
  width: number
  height: number
  fps: number
  type: CameraSourceType
  name: string
  [key: string]: unknown
}

export interface CameraSourceDescriptor {
  id: string
  name: string
  type: CameraSourceType
  available: boolean
  metadata: CameraSourceMetadata
}

export interface CameraSourcesResponse {
  active_id: string
  sources: CameraSourceDescriptor[]
}

export interface CameraSourceStatus {
  source_id: string | null
  name: string | null
  type: CameraSourceType | null
  opened: boolean
  connected: boolean
  state: 'connected' | 'disconnected' | 'error'
  error: string | null
  metadata: CameraSourceMetadata | null
  discovery_completed: boolean
  mock_graph: MockGraphStatus | null
  frame_id?: number | null
}

export interface CameraSourceSelectionResponse {
  active_id: string
  metadata: CameraSourceMetadata
}

export interface MockGraphHotspot {
  id: string
  label: string
  x: number
  y: number
  width: number
  height: number
  next_state: string
}

export interface MockGraphTap {
  x: number
  y: number
  state: string
  hit: boolean
  hotspot_id: string | null
  timestamp: string
}

export interface MockGraphTransition {
  from_state: string
  to_state: string
  trigger: string
  hotspot_id: string | null
  label: string | null
  timestamp: string
}

export interface MockGraphNode {
  id: string
  image: string
  width: number
  height: number
  hotspots: MockGraphHotspot[]
}

export interface MockGraphEdge {
  id: string
  from_state: string
  to_state: string
  hotspot_id: string
  label: string
}

export interface MockGraphStatus {
  schema_version: number
  id: string
  name: string
  description: string
  screen_width: number
  screen_height: number
  initial_state: string
  current_state: string
  previous_state: string | null
  available_hotspots: MockGraphHotspot[]
  last_tap: MockGraphTap | null
  last_transition: MockGraphTransition | null
  states: MockGraphNode[]
  edges: MockGraphEdge[]
}
