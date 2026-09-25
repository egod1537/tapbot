import type { AndroidPointerPoint } from '../../types/android-debug'

export const POINTER_SAMPLE_DISTANCE_PX = 4
export const POINTER_SAMPLE_INTERVAL_MS = 12
export const POINTER_MAX_POINTS = 256
export const TAP_DISTANCE_PX = 8
export const TAP_MAX_DURATION_MS = 300

interface RectLike {
  left: number
  top: number
  width: number
  height: number
}

export function mapPointerToFrame(
  clientX: number,
  clientY: number,
  bounds: RectLike,
  frameWidth: number,
  frameHeight: number,
): { x: number; y: number } | null {
  if (frameWidth <= 0 || frameHeight <= 0 || bounds.width <= 0 || bounds.height <= 0)
    return null
  const scale = Math.min(bounds.width / frameWidth, bounds.height / frameHeight)
  const renderedWidth = frameWidth * scale
  const renderedHeight = frameHeight * scale
  const offsetX = (bounds.width - renderedWidth) / 2
  const offsetY = (bounds.height - renderedHeight) / 2
  const x = (clientX - bounds.left - offsetX) / scale
  const y = (clientY - bounds.top - offsetY) / scale
  if (x < 0 || y < 0 || x >= frameWidth || y >= frameHeight) return null
  return { x, y }
}

export function appendSampledPoint(
  points: AndroidPointerPoint[],
  point: AndroidPointerPoint,
  options: { force?: boolean; maxPoints?: number } = {},
): AndroidPointerPoint[] {
  const last = points.at(-1)
  if (!last) return [point]
  const distance = Math.hypot(point.x - last.x, point.y - last.y)
  const elapsed = point.t_ms - last.t_ms
  if (
    !options.force &&
    distance < POINTER_SAMPLE_DISTANCE_PX &&
    elapsed < POINTER_SAMPLE_INTERVAL_MS
  ) {
    return points
  }
  const combined = [...points, point]
  const maxPoints = options.maxPoints ?? POINTER_MAX_POINTS
  if (combined.length <= maxPoints) return combined
  const combinedFirst = combined[0]
  const combinedLast = combined.at(-1)
  if (!combinedFirst || !combinedLast) return combined
  const sampled: AndroidPointerPoint[] = [combinedFirst]
  for (let index = 1; index < maxPoints - 1; index += 1) {
    const sourceIndex = Math.round((index * (combined.length - 1)) / (maxPoints - 1))
    const source = combined[sourceIndex]
    if (source) sampled.push(source)
  }
  sampled.push(combinedLast)
  return sampled
}

export function isTapPath(points: AndroidPointerPoint[]): boolean {
  if (points.length < 2) return true
  const first = points[0]
  const last = points.at(-1)
  if (!first || !last) return true
  const duration = last.t_ms - first.t_ms
  const maxDistance = points.reduce(
    (maximum, point) =>
      Math.max(maximum, Math.hypot(point.x - first.x, point.y - first.y)),
    0,
  )
  return maxDistance < TAP_DISTANCE_PX && duration < TAP_MAX_DURATION_MS
}
