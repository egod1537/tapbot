import { describe, expect, it } from 'vitest'
import {
  appendSampledPoint,
  isTapPath,
  mapPointerToFrame,
  POINTER_MAX_POINTS,
} from './pointer-gesture'

describe('pointer gesture recorder', () => {
  it('maps pointer coordinates through a contained frame', () => {
    expect(
      mapPointerToFrame(
        150,
        100,
        { left: 10, top: 20, width: 280, height: 160 },
        200,
        100,
      ),
    ).toEqual({ x: 100, y: 50 })
    expect(
      mapPointerToFrame(
        15,
        25,
        { left: 10, top: 20, width: 280, height: 160 },
        200,
        100,
      ),
    ).toBeNull()
  })

  it('samples small moves and resamples over the point limit', () => {
    const first = [{ x: 0, y: 0, t_ms: 0 }]
    expect(appendSampledPoint(first, { x: 1, y: 1, t_ms: 5 })).toBe(first)

    let points = first
    for (let index = 1; index <= POINTER_MAX_POINTS + 20; index += 1) {
      points = appendSampledPoint(points, {
        x: index * 5,
        y: 0,
        t_ms: index * 12,
      })
    }
    expect(points).toHaveLength(POINTER_MAX_POINTS)
    expect(points[0]).toEqual(first[0])
    expect(points.at(-1)?.x).toBe((POINTER_MAX_POINTS + 20) * 5)
  })

  it('distinguishes a click from a drag', () => {
    expect(
      isTapPath([
        { x: 10, y: 10, t_ms: 0 },
        { x: 14, y: 12, t_ms: 100 },
      ]),
    ).toBe(true)
    expect(
      isTapPath([
        { x: 10, y: 10, t_ms: 0 },
        { x: 10, y: 80, t_ms: 100 },
      ]),
    ).toBe(false)
  })
})
