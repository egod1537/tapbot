// @vitest-environment jsdom

import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type {
  AndroidDebugState,
  AndroidProxyStatus,
  AndroidUiNode,
  AndroidUiTree,
} from '../../types/android-debug'
import type { VisionDetection } from '../../types/vision'
import { AndroidDebugWorkspace } from './AndroidDebugWorkspace'
import type { useAndroidDebug } from './useAndroidDebug'

vi.mock('./android-api', () => ({
  androidApi: {
    streamUrl: vi.fn((deviceId: string) => `/api/android/${deviceId}/stream`),
    screenshotUrl: vi.fn((deviceId: string) => `/api/android/${deviceId}/screenshot`),
  },
}))

const status = (connected = true): AndroidProxyStatus => ({
  device_id: 'device-a',
  name: 'Note10',
  configured: true,
  connected,
  error: connected ? null : 'offline',
  agent: connected
    ? {
        accessibility_enabled: true,
        capture_ready: true,
        stream_running: true,
        remote_control_enabled: true,
        agent_version: 'test',
        device: { width: 200, height: 100, rotation: 0, density: 3 },
      }
    : null,
  stream: connected
    ? {
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
      }
    : null,
  macro_status: 'IDLE',
})

const detections = (count: number): VisionDetection[] =>
  Array.from({ length: count }, (_, index) => ({
    id: `detection-${index.toString()}`,
    label: `button-${index.toString()}`,
    bbox: { x: index, y: index, width: 10, height: 10 },
    center: { x: index + 5, y: index + 5 },
    confidence: 0.9,
    detector_type: 'test',
    detector_name: 'Test detector',
  }))

const debugState = (items: VisionDetection[] = []): AndroidDebugState => ({
  device_id: 'device-a',
  source_id: 'android:device-a',
  state: { current: 'home', previous: null, confidence: 1 },
  macro: { id: 'macro-a', status: 'IDLE', step_index: 0 },
  frame: {
    frame_id: '1',
    source_id: 'android:device-a',
    captured_at: '2026-09-25T00:00:00Z',
    width: 200,
    height: 100,
    rotation: 0,
    already_canonical: true,
  },
  detections: items,
  vision_latency_ms: 1,
  decision: {
    classifier: { state: 'home', confidence: 1 },
    vlm: null,
    target: null,
    final_action: null,
    blocked_reason: null,
  },
  last_action: null,
  last_action_result: null,
  error: null,
})

const node = (index: number): AndroidUiNode => ({
  node_id: `n${index.toString()}`,
  parent_id: null,
  depth: 0,
  class_name: 'android.widget.Button',
  text: `Button ${index.toString()}`,
  content_description: null,
  view_id_resource_name: `example:id/button${index.toString()}`,
  package_name: 'example',
  bounds: { left: 0, top: 0, right: 20, bottom: 20 },
  clickable: true,
  enabled: true,
  focusable: false,
  focused: false,
  selected: false,
  checked: false,
  checkable: false,
  scrollable: false,
  editable: false,
  visible_to_user: true,
  password: false,
  child_count: 0,
  children: [],
})

const tree = (count: number): AndroidUiTree => {
  const nodes = Array.from({ length: count }, (_, index) => ({
    ...node(index),
    parent_id: index === 0 ? null : 'n0',
    depth: index === 0 ? 0 : 1,
  }))
  const root = {
    ...(nodes[0] ?? node(0)),
    child_count: Math.max(0, nodes.length - 1),
    children: nodes.slice(1),
  }
  return {
    ok: true,
    request_id: 'tree-a',
    device_id: 'device-a',
    source_id: 'android:device-a',
    captured_at: '2026-09-25T00:00:00Z',
    package_name: 'example',
    window_title: null,
    rotation: 0,
    screen_width: 200,
    screen_height: 100,
    node_count: count,
    truncated: false,
    root,
    nodes,
  }
}

type Controller = ReturnType<typeof useAndroidDebug>

function controller(overrides: Record<string, unknown> = {}): Controller {
  return {
    deviceId: 'device-a',
    status: status(),
    debug: debugState(),
    events: [],
    uiTree: null,
    uiTreeError: null,
    uiTreeLoading: false,
    selectedUiNodeId: null,
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
    setSelectedUiNodeId: vi.fn(),
    setStreamFailed: vi.fn(),
    reconnectStream: vi.fn(),
    refreshUiTree: vi.fn(() => Promise.resolve()),
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
    ...overrides,
  }
}

const devices = [
  {
    id: 'device-a',
    name: 'Note10',
    connected: true,
    last_seen_at: null,
    capture_ready: true,
    stream_running: true,
    accessibility_enabled: true,
    remote_control_enabled: true,
    macro_status: 'IDLE' as const,
    last_error: null,
  },
]

beforeEach(() => vi.useFakeTimers())
afterEach(() => {
  cleanup()
  vi.useRealTimers()
  vi.clearAllMocks()
})

describe('Android live viewport layout stability', () => {
  it('preserves the same viewport through status, message, overlay, and tree updates', async () => {
    const view = render(
      <AndroidDebugWorkspace
        controller={controller({ status: null, debug: null })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    const stage = view.container.querySelector('.android-live-stage')
    const image = stage?.querySelector('img')
    const overlay = stage?.querySelector('svg')

    expect(stage).toBeTruthy()
    expect(view.container.querySelector('.android-live-shell')).toBeTruthy()

    view.rerender(
      <AndroidDebugWorkspace
        controller={controller({ error: 'temporary error', notice: 'done' })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    await act(async () => vi.runOnlyPendingTimersAsync())
    expect(view.container.querySelector('.android-live-stage')).toBe(stage)
    expect(stage?.querySelector('img')).toBe(image)
    expect(stage?.querySelector('svg')).toBe(overlay)
    expect(
      view.container.querySelector('.android-debug-side-panel .bp6-callout'),
    ).toBeTruthy()

    view.rerender(
      <AndroidDebugWorkspace
        controller={controller({ debug: debugState(detections(10)), uiTree: tree(60) })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    expect(view.container.querySelector('.android-live-stage')).toBe(stage)
    expect(stage?.querySelectorAll('.android-detection-box')).toHaveLength(10)
    expect(view.container.querySelectorAll('.android-hierarchy-row')).toHaveLength(60)
  })

  it('keeps the stage and image slot when stream falls back to screenshots', async () => {
    const view = render(
      <AndroidDebugWorkspace
        controller={controller()}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    await act(async () => vi.runOnlyPendingTimersAsync())
    const stage = view.container.querySelector('.android-live-stage')
    const image = stage?.querySelector('img')
    expect(image?.getAttribute('src')).toContain('/stream')

    view.rerender(
      <AndroidDebugWorkspace
        controller={controller({ streamFailed: true })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )

    expect(view.container.querySelector('.android-live-stage')).toBe(stage)
    expect(stage?.querySelector('img')).toBe(image)
    expect(image?.getAttribute('src')).toContain('/screenshot')
    expect(stage?.getAttribute('data-geometry')).toBe('200x100')
  })

  it('uses the pointerdown geometry snapshot through polling updates', async () => {
    const gesture = vi.fn()
    const view = render(
      <AndroidDebugWorkspace
        controller={controller({ manualTapEnabled: true, gesture })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    await act(async () => vi.runOnlyPendingTimersAsync())
    const stage = view.container.querySelector('.android-live-stage') as HTMLDivElement
    const bounds = vi.spyOn(stage, 'getBoundingClientRect')
    bounds.mockReturnValue({
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
    fireEvent.pointerDown(stage, {
      pointerId: 9,
      button: 0,
      clientX: 20,
      clientY: 80,
    })

    const geometryUpdate = status()
    if (geometryUpdate.stream) {
      geometryUpdate.stream = {
        ...geometryUpdate.stream,
        width: 400,
        height: 100,
      }
    }

    view.rerender(
      <AndroidDebugWorkspace
        controller={controller({
          manualTapEnabled: true,
          gesture,
          status: geometryUpdate,
          debug: debugState(detections(10)),
        })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    bounds.mockReturnValue({
      left: 0,
      top: 0,
      width: 400,
      height: 100,
      right: 400,
      bottom: 100,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })
    fireEvent.pointerUp(stage, {
      pointerId: 9,
      button: 0,
      clientX: 180,
      clientY: 20,
    })

    const path = gesture.mock.calls[0]?.[0] as Array<{ x: number; y: number }>
    expect(path.at(-1)).toMatchObject({ x: 180, y: 20 })
    await act(async () => vi.runOnlyPendingTimersAsync())
    expect(stage.getAttribute('data-geometry')).toBe('400x100')
  })
})

describe('Unity-style UI tree inspector', () => {
  const nestedTree = (options?: {
    hiddenLeaf?: boolean
    truncated?: boolean
  }): AndroidUiTree => {
    const root = {
      ...node(0),
      class_name: 'android.widget.FrameLayout',
      text: null,
      clickable: false,
      child_count: 1,
    }
    const branch = {
      ...node(1),
      parent_id: root.node_id,
      depth: 1,
      class_name: 'android.widget.LinearLayout',
      text: 'Settings group',
      clickable: false,
      child_count: 1,
    }
    const leaf = {
      ...node(2),
      parent_id: branch.node_id,
      depth: 2,
      text: 'Photo verification',
      bounds: { left: 40, top: 20, right: 160, bottom: 70 },
      visible_to_user: !options?.hiddenLeaf,
    }
    branch.children = [leaf]
    root.children = [branch]
    return {
      ...tree(3),
      truncated: options?.truncated ?? false,
      root,
      nodes: [root, branch, leaf],
    }
  }

  it('expands hierarchy rows, searches fields, and applies visibility filters', () => {
    const snapshot = nestedTree({ hiddenLeaf: true })
    const view = render(
      <AndroidDebugWorkspace
        controller={controller({ uiTree: snapshot })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )

    expect(view.container.querySelectorAll('.android-hierarchy-row')).toHaveLength(2)
    fireEvent.click(view.getByLabelText('Visible'))
    fireEvent.click(view.getByLabelText('Expand Settings group'))
    expect(view.getByText('“Photo verification”')).toBeTruthy()

    fireEvent.change(view.getByLabelText('Search UI tree'), {
      target: { value: 'photo verification' },
    })
    expect(view.container.querySelectorAll('.is-search-match')).toHaveLength(1)
  })

  it('selects a node, highlights its bounds, previews a selector, and taps center', () => {
    const snapshot = nestedTree()
    const setSelectedUiNodeId = vi.fn()
    const tap = vi.fn()
    const initial = controller({ uiTree: snapshot, setSelectedUiNodeId, tap })
    const view = render(
      <AndroidDebugWorkspace
        controller={initial}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )

    fireEvent.click(view.getByLabelText('Expand Settings group'))
    fireEvent.click(view.getByText('“Photo verification”'))
    expect(setSelectedUiNodeId).toHaveBeenCalledWith('n2')

    view.rerender(
      <AndroidDebugWorkspace
        controller={controller({
          uiTree: snapshot,
          selectedUiNodeId: 'n2',
          setSelectedUiNodeId,
          tap,
        })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )

    const highlight = view.container.querySelector('.android-ui-node-box rect')
    expect(highlight?.getAttribute('x')).toBe('40')
    expect(highlight?.getAttribute('width')).toBe('120')
    expect(view.getByDisplayValue(/viewId == "example:id\/button2"/)).toBeTruthy()
    fireEvent.click(view.getByRole('button', { name: 'Tap Center' }))
    expect(tap).toHaveBeenCalledWith(100, 45)
  })

  it('keeps unavailable and truncated states inside the inspector', () => {
    const view = render(
      <AndroidDebugWorkspace
        controller={controller({
          uiTree: null,
          uiTreeError: 'No active accessibility root.',
        })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    expect(view.getByText('UI tree unavailable')).toBeTruthy()
    expect(view.getByText('No active accessibility root.')).toBeTruthy()

    view.rerender(
      <AndroidDebugWorkspace
        controller={controller({ uiTree: nestedTree({ truncated: true }) })}
        devices={devices}
        onDeviceChange={vi.fn()}
      />,
    )
    expect(view.getByText('TRUNCATED')).toBeTruthy()
  })
})
