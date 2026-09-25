// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest'
import { androidApi } from './android-api'

describe('androidApi device routing', () => {
  it('namespaces stream, screenshot, and vision URLs by device id', () => {
    expect(androidApi.streamUrl('device-a', 123)).toContain(
      '/android/device-a/stream?v=123',
    )
    expect(androidApi.screenshotUrl('device b', 'frame/1')).toContain(
      '/android/device%20b/screenshot?v=frame%2F1',
    )
    expect(androidApi.visionFrameUrl('device-a', 'frame/1')).toContain(
      '/android/device-a/vision/frame?frame_id=frame%2F1',
    )
  })

  it('requests the selected device UI tree through the PC backend', async () => {
    let requestedUrl: string | null = null
    const fetch = vi.fn((input: RequestInfo | URL) => {
      requestedUrl =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url
      return Promise.resolve(
        new Response(
          JSON.stringify({
            ok: true,
            request_id: 'tree-1',
            device_id: 'device a',
            source_id: 'android:device a',
            captured_at: '2026-09-25T00:00:00Z',
            package_name: null,
            window_title: null,
            rotation: 0,
            screen_width: 100,
            screen_height: 200,
            node_count: 0,
            truncated: false,
            root: {},
            nodes: [],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      )
    })
    vi.stubGlobal('fetch', fetch)

    await androidApi.uiTree('device a')

    expect(requestedUrl).toContain('/android/device%20a/ui-tree')
    vi.unstubAllGlobals()
  })

  it('posts a complete pointer trajectory to the selected device', async () => {
    let body = ''
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        body = typeof init?.body === 'string' ? init.body : ''
        return Promise.resolve(
          new Response(
            JSON.stringify({ ok: true, device_id: 'device-a', result: {} }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        )
      }),
    )

    await androidApi.gesture('device-a', [
      { x: 10, y: 20, t_ms: 0 },
      { x: 30, y: 40, t_ms: 120 },
    ])

    expect(JSON.parse(body)).toEqual({
      points: [
        { x: 10, y: 20, t_ms: 0 },
        { x: 30, y: 40, t_ms: 120 },
      ],
    })
    vi.unstubAllGlobals()
  })
})
