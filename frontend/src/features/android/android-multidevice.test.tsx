// @vitest-environment jsdom

import { act, fireEvent, render, renderHook, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  AndroidDeviceSummary,
  AndroidProxyStatus,
} from '../../types/android-debug'
import { AndroidDebugWorkspace } from './AndroidDebugWorkspace'
import { androidApi } from './android-api'
import { useAndroidDebug } from './useAndroidDebug'

vi.mock('./android-api', () => ({
  androidApi: {
    status: vi.fn(),
    debugState: vi.fn(),
    uiTree: vi.fn(),
    runVision: vi.fn(),
    saveScreenshot: vi.fn(),
    tap: vi.fn(),
    gesture: vi.fn(),
    back: vi.fn(),
    home: vi.fn(),
    macroStart: vi.fn(),
    macroPause: vi.fn(),
    macroStop: vi.fn(),
    macroReset: vi.fn(),
    macroStep: vi.fn(),
    streamUrl: vi.fn((deviceId: string) => `/api/android/${deviceId}/stream`),
    screenshotUrl: vi.fn((deviceId: string) => `/api/android/${deviceId}/screenshot`),
  },
}))

vi.mock('../timeline/timeline-api', () => ({
  timelineApi: { entries: vi.fn(() => Promise.resolve({ entries: [] })) },
}))

const offlineStatus = (deviceId: string): AndroidProxyStatus => ({
  device_id: deviceId,
  name: deviceId,
  configured: true,
  connected: false,
  error: null,
  agent: null,
  stream: null,
  macro_status: 'IDLE',
})

const devices: AndroidDeviceSummary[] = [
  {
    id: 'device-a',
    name: 'Note10',
    connected: true,
    last_seen_at: null,
    capture_ready: true,
    stream_running: true,
    accessibility_enabled: true,
    remote_control_enabled: true,
    macro_status: 'RUNNING',
    last_error: null,
  },
  {
    id: 'device-b',
    name: 'S20',
    connected: false,
    last_seen_at: null,
    capture_ready: false,
    stream_running: false,
    accessibility_enabled: false,
    remote_control_enabled: false,
    macro_status: 'IDLE',
    last_error: 'offline',
  },
]

beforeEach(() => {
  vi.mocked(androidApi.status).mockImplementation((deviceId) =>
    Promise.resolve(offlineStatus(deviceId)),
  )
  vi.mocked(androidApi.debugState).mockImplementation((deviceId) =>
    Promise.resolve({
      device_id: deviceId,
      source_id: `android:${deviceId}`,
      state: { current: 'unknown', previous: null, confidence: 0 },
      macro: { id: `macro-${deviceId}`, status: 'IDLE', step_index: 0 },
      frame: null,
      detections: [],
      vision_latency_ms: null,
      decision: {
        classifier: { state: 'unknown', confidence: 0 },
        vlm: null,
        target: null,
        final_action: null,
        blocked_reason: null,
      },
      last_action: null,
      last_action_result: null,
      error: null,
    }),
  )
  vi.mocked(androidApi.tap).mockResolvedValue({
    ok: true,
    device_id: 'device-a',
    result: {},
  })
  vi.mocked(androidApi.gesture).mockResolvedValue({
    ok: true,
    device_id: 'device-a',
    result: {},
  })
})

afterEach(() => {
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('multi-device Android debug UI', () => {
  it('shows device summaries and changes the selected device', () => {
    const onDeviceChange = vi.fn()
    const controller = {
      deviceId: 'device-a',
      status: offlineStatus('device-a'),
      debug: null,
      events: [],
      error: null,
      notice: null,
      busy: null,
      manualTapEnabled: false,
      selectedDetectionId: null,
      highlightedDetectionId: null,
      streamNonce: 1,
      streamFailed: false,
      setManualTapEnabled: vi.fn(),
      setSelectedDetectionId: vi.fn(),
      setHighlightedDetectionId: vi.fn(),
      setStreamFailed: vi.fn(),
      reconnectStream: vi.fn(),
      tap: vi.fn(),
      gesture: vi.fn(),
      saveScreenshot: vi.fn(),
      back: vi.fn(),
      home: vi.fn(),
      macroStart: vi.fn(),
      macroPause: vi.fn(),
      macroStop: vi.fn(),
      macroReset: vi.fn(),
      macroStep: vi.fn(),
    } as unknown as ReturnType<typeof useAndroidDebug>

    render(
      <AndroidDebugWorkspace
        controller={controller}
        devices={devices}
        onDeviceChange={onDeviceChange}
      />,
    )

    const selector = screen.getByLabelText('Android Device')
    expect(screen.getByText(/Note10 · ONLINE · LIVE · RUNNING/)).toBeTruthy()
    expect(screen.getByText(/S20 · OFFLINE · OFF · IDLE/)).toBeTruthy()
    fireEvent.change(selector, { target: { value: 'device-b' } })
    expect(onDeviceChange).toHaveBeenCalledWith('device-b')
  })

  it('cancels old polling and clears stale overlay selection on device change', async () => {
    vi.useFakeTimers()
    const signals: AbortSignal[] = []
    vi.mocked(androidApi.status).mockImplementation((deviceId, signal) => {
      if (signal) signals.push(signal)
      return Promise.resolve(offlineStatus(deviceId))
    })
    const { result, rerender } = renderHook(
      ({ deviceId }: { deviceId: string }) => useAndroidDebug(deviceId),
      { initialProps: { deviceId: 'device-a' } },
    )
    await act(async () => vi.advanceTimersByTimeAsync(0))
    act(() => {
      result.current.setSelectedDetectionId('old-selection')
      result.current.setHighlightedDetectionId('old-highlight')
    })

    rerender({ deviceId: 'device-b' })
    await act(async () => vi.advanceTimersByTimeAsync(0))

    expect(signals[0]?.aborted).toBe(true)
    expect(result.current.selectedDetectionId).toBeNull()
    expect(result.current.highlightedDetectionId).toBeNull()
    expect(result.current.debug?.device_id ?? null).not.toBe('device-a')
  })

  it('sends actions only to the selected device id', async () => {
    const { result } = renderHook(() => useAndroidDebug('device-a'))
    await act(async () => {
      await result.current.tap(12, 34)
    })
    expect(androidApi.tap).toHaveBeenCalledWith('device-a', 12, 34)
  })

  it('records click, drag, and cancellation as pointer gestures', () => {
    const tap = vi.fn()
    const gesture = vi.fn()
    const status = {
      ...offlineStatus('device-a'),
      connected: true,
      agent: {
        accessibility_enabled: true,
        capture_ready: true,
        stream_running: true,
        remote_control_enabled: true,
        agent_version: 'test',
        device: { width: 200, height: 100, rotation: 0, density: 3 },
      },
      stream: {
        running: true,
        codec: 'mjpeg',
        transport: 'http-multipart',
        width: 200,
        height: 100,
        rotation: 0,
        fps: 20,
        target_fps: 20,
        bitrate: 1000,
        clients: 1,
        capture_latency_ms: 1,
        encode_latency_ms: 1,
        frame_age_ms: 1,
      },
    } satisfies AndroidProxyStatus
    const makeController = (overrides: Record<string, unknown> = {}) =>
      ({
        deviceId: 'device-a',
        status,
        debug: null,
        events: [],
        uiTree: null,
        uiTreeError: null,
        selectedUiNodeId: null,
        error: null,
        notice: null,
        busy: null,
        manualTapEnabled: true,
        selectedDetectionId: null,
        highlightedDetectionId: null,
        streamNonce: 1,
        streamFailed: false,
        setManualTapEnabled: vi.fn(),
        setSelectedDetectionId: vi.fn(),
        setHighlightedDetectionId: vi.fn(),
        setSelectedUiNodeId: vi.fn(),
        setStreamFailed: vi.fn(),
        reconnectStream: vi.fn(),
        tap,
        gesture,
        saveScreenshot: vi.fn(),
        back: vi.fn(),
        home: vi.fn(),
        macroStart: vi.fn(),
        macroPause: vi.fn(),
        macroStop: vi.fn(),
        macroReset: vi.fn(),
        macroStep: vi.fn(),
        ...overrides,
      }) as unknown as ReturnType<typeof useAndroidDebug>

    const view = render(
      <AndroidDebugWorkspace
        controller={makeController()}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    let stage = view.container.querySelector('.android-live-stage') as HTMLDivElement
    vi.spyOn(stage, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      top: 0,
      width: 200,
      height: 100,
      right: 200,
      bottom: 100,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })

    fireEvent.pointerDown(stage, { pointerId: 1, button: 0, clientX: 20, clientY: 20 })
    fireEvent.pointerUp(stage, { pointerId: 1, button: 0, clientX: 21, clientY: 20 })
    expect(tap).toHaveBeenCalledWith(20, 20)

    fireEvent.pointerDown(stage, { pointerId: 2, button: 0, clientX: 20, clientY: 80 })
    fireEvent.pointerMove(stage, { pointerId: 2, clientX: 30, clientY: 50 })
    fireEvent.pointerUp(stage, { pointerId: 2, button: 0, clientX: 40, clientY: 20 })
    expect(gesture).toHaveBeenCalledTimes(1)
    expect(gesture.mock.calls[0]?.[0]).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ x: 20, y: 80, t_ms: 0 }),
        expect.objectContaining({ x: 40, y: 20 }),
      ]),
    )

    fireEvent.pointerDown(stage, { pointerId: 3, button: 0, clientX: 20, clientY: 80 })
    fireEvent.pointerCancel(stage, { pointerId: 3 })
    fireEvent.pointerUp(stage, { pointerId: 3, button: 0, clientX: 40, clientY: 20 })
    expect(gesture).toHaveBeenCalledTimes(1)

    fireEvent.pointerDown(stage, { pointerId: 4, button: 0, clientX: 20, clientY: 80 })
    view.rerender(
      <AndroidDebugWorkspace
        controller={makeController({ deviceId: 'device-b' })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    stage = view.container.querySelector('.android-live-stage') as HTMLDivElement
    fireEvent.pointerUp(stage, { pointerId: 4, button: 0, clientX: 40, clientY: 20 })
    expect(gesture).toHaveBeenCalledTimes(1)

    view.rerender(
      <AndroidDebugWorkspace
        controller={makeController()}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    stage = view.container.querySelector('.android-live-stage') as HTMLDivElement
    vi.spyOn(stage, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      top: 0,
      width: 200,
      height: 100,
      right: 200,
      bottom: 100,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    fireEvent.pointerDown(stage, { pointerId: 5, button: 0, clientX: 20, clientY: 80 })
    view.rerender(
      <AndroidDebugWorkspace
        controller={makeController({ streamFailed: true })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    stage = view.container.querySelector('.android-live-stage') as HTMLDivElement
    fireEvent.pointerUp(stage, { pointerId: 5, button: 0, clientX: 40, clientY: 20 })
    expect(gesture).toHaveBeenCalledTimes(1)
  })
})
