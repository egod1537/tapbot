import type { FramePoint } from '../../types/camera'

function cross(a: FramePoint, b: FramePoint, c: FramePoint): number {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
}

function segmentsIntersect(
  a: FramePoint,
  b: FramePoint,
  c: FramePoint,
  d: FramePoint,
): boolean {
  const abC = cross(a, b, c)
  const abD = cross(a, b, d)
  const cdA = cross(c, d, a)
  const cdB = cross(c, d, b)
  return abC * abD < 0 && cdA * cdB < 0
}

export function quadrilateralError(
  points: FramePoint[],
  minimumArea: number,
): string | null {
  if (points.length !== 4) return 'Select exactly four points.'
  const [tl, tr, br, bl] = points
  if (!tl || !tr || !br || !bl) return 'Select exactly four points.'

  const unique = new Set(points.map(({ x, y }) => `${x.toFixed(4)}:${y.toFixed(4)}`))
  if (unique.size !== 4) return 'All four points must be unique.'
  if (segmentsIntersect(tl, tr, br, bl) || segmentsIntersect(tr, br, bl, tl)) {
    return 'Corner edges must not cross.'
  }

  const signedArea =
    (tl.x * tr.y -
      tr.x * tl.y +
      tr.x * br.y -
      br.x * tr.y +
      br.x * bl.y -
      bl.x * br.y +
      bl.x * tl.y -
      tl.x * bl.y) /
    2
  if (!Number.isFinite(signedArea) || Math.abs(signedArea) <= minimumArea) {
    return 'Corners must form a non-degenerate quadrilateral.'
  }
  if (signedArea <= 0) {
    return 'Select corners clockwise in TL → TR → BR → BL order.'
  }
  return null
}

export function pointerToFrame(
  event: React.MouseEvent<HTMLElement>,
  width: number,
  height: number,
): FramePoint {
  const rect = event.currentTarget.getBoundingClientRect()
  return {
    x: Math.min(width, Math.max(0, ((event.clientX - rect.left) / rect.width) * width)),
    y: Math.min(
      height,
      Math.max(0, ((event.clientY - rect.top) / rect.height) * height),
    ),
  }
}
