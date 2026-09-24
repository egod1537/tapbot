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
