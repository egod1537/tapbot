import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api-client'
import type {
  AndroidDebugState,
  AndroidPointerPoint,
  AndroidProxyStatus,
  AndroidUiNode,
  AndroidUiTree,
} from '../../types/android-debug'
import type { TimelineEvent } from '../../types/timeline'
import { timelineApi } from '../timeline/timeline-api'
import { androidApi } from './android-api'

const STATUS_INTERVAL_MS = 2_000
const DEBUG_INTERVAL_MS = 1_000
const VISION_INTERVAL_MS = 1_500
const UI_TREE_INTERVAL_MS = 1_000

function message(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message
  return 'Android debug request failed.'
}

function uiNodeFingerprint(node: AndroidUiNode): string {
  return JSON.stringify([
    node.view_id_resource_name,
    node.content_description,
    node.text,
    node.class_name,
    node.depth,
  ])
}

export function useAndroidDebug(deviceId: string | null) {
  const [status, setStatus] = useState<AndroidProxyStatus | null>(null)
  const [debug, setDebug] = useState<AndroidDebugState | null>(null)
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [uiTree, setUiTree] = useState<AndroidUiTree | null>(null)
  const [uiTreeError, setUiTreeError] = useState<string | null>(null)
  const [uiTreeLoading, setUiTreeLoading] = useState(false)
  const [selectedUiNodeId, setSelectedUiNodeId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [manualTapEnabled, setManualTapEnabled] = useState(false)
  const [selectedDetectionId, setSelectedDetectionId] = useState<string | null>(null)
  const [highlightedDetectionId, setHighlightedDetectionId] = useState<string | null>(
    null,
  )
  const [streamNonce, setStreamNonce] = useState(() => Date.now())
  const [streamFailed, setStreamFailed] = useState(false)
  const visionInFlight = useRef(false)
  const uiTreeInFlight = useRef(false)
  const uiTreeRef = useRef<AndroidUiTree | null>(null)
  const selectedUiNodeFingerprint = useRef<string | null>(null)
  const deviceGeneration = useRef(0)
  const activeStatus = status?.device_id === deviceId ? status : null
  const activeDebug = debug?.device_id === deviceId ? debug : null
  const activeUiTree = uiTree?.device_id === deviceId ? uiTree : null

  useEffect(() => {
    deviceGeneration.current += 1
    visionInFlight.current = false
    const reset = window.setTimeout(() => {
      setStatus(null)
      setDebug(null)
      setEvents([])
      setUiTree(null)
      setUiTreeError(null)
      setUiTreeLoading(false)
      setSelectedUiNodeId(null)
      uiTreeInFlight.current = false
      uiTreeRef.current = null
      selectedUiNodeFingerprint.current = null
      setError(null)
      setNotice(null)
      setBusy(null)
      setManualTapEnabled(false)
      setSelectedDetectionId(null)
      setHighlightedDetectionId(null)
      setStreamFailed(false)
      setStreamNonce(Date.now())
    }, 0)
    return () => window.clearTimeout(reset)
  }, [deviceId])

  const refreshStatus = useCallback(
    async (signal?: AbortSignal) => {
      if (!deviceId) return
      try {
        const next = await androidApi.status(deviceId, signal)
        setStatus(next)
        setError(next.error)
      } catch (caught) {
        if (signal?.aborted) return
        setError(message(caught))
      }
    },
    [deviceId],
  )

  const refreshDebug = useCallback(
    async (signal?: AbortSignal) => {
      if (!deviceId) return
      try {
        const [nextDebug, log] = await Promise.all([
          androidApi.debugState(deviceId, signal),
          timelineApi.entries(),
        ])
        setDebug(nextDebug)
        setEvents(
          log.entries
            .filter((entry) => entry.payload.device_id === deviceId)
            .slice(-40)
            .reverse(),
        )
      } catch (caught) {
        if (signal?.aborted) return
        if (caught instanceof ApiError && caught.status === 503) return
        setError(message(caught))
      }
    },
    [deviceId],
  )

  useEffect(() => {
    if (!deviceId) return
    const controller = new AbortController()
    const firstRequest = window.setTimeout(() => {
      void refreshStatus(controller.signal)
      void refreshDebug(controller.signal)
    }, 0)
    const statusTimer = window.setInterval(
      () => void refreshStatus(controller.signal),
      STATUS_INTERVAL_MS,
    )
    const debugTimer = window.setInterval(
      () => void refreshDebug(controller.signal),
      DEBUG_INTERVAL_MS,
    )
    return () => {
      controller.abort()
      window.clearTimeout(firstRequest)
      window.clearInterval(statusTimer)
      window.clearInterval(debugTimer)
    }
  }, [deviceId, refreshDebug, refreshStatus])

  useEffect(() => {
    if (!deviceId || !activeStatus?.connected || !activeStatus.agent?.capture_ready)
      return
    const controller = new AbortController()
    let cancelled = false
    const run = async () => {
      if (visionInFlight.current || cancelled) return
      visionInFlight.current = true
      try {
        const next = await androidApi.runVision(deviceId, controller.signal)
        if (!cancelled) setDebug(next)
      } catch (caught) {
        if (!cancelled) setError(message(caught))
      } finally {
        visionInFlight.current = false
      }
    }
    void run()
    const timer = window.setInterval(() => void run(), VISION_INTERVAL_MS)
    return () => {
      cancelled = true
      controller.abort()
      window.clearInterval(timer)
    }
  }, [activeStatus?.agent?.capture_ready, activeStatus?.connected, deviceId])

  const refreshUiTree = useCallback(
    async (signal?: AbortSignal) => {
      if (!deviceId || uiTreeInFlight.current) return
      uiTreeInFlight.current = true
      setUiTreeLoading(true)
      try {
        const next = await androidApi.uiTree(deviceId, signal)
        if (signal?.aborted) return
        uiTreeRef.current = next
        const fingerprint = selectedUiNodeFingerprint.current
        if (fingerprint) {
          const restored = next.nodes.find(
            (node) => uiNodeFingerprint(node) === fingerprint,
          )
          setSelectedUiNodeId(restored?.node_id ?? null)
          if (!restored) selectedUiNodeFingerprint.current = null
        }
        setUiTree(next)
        setUiTreeError(null)
      } catch (caught) {
        if (!signal?.aborted) setUiTreeError(message(caught))
      } finally {
        uiTreeInFlight.current = false
        if (!signal?.aborted) setUiTreeLoading(false)
      }
    },
    [deviceId],
  )

  useEffect(() => {
    if (
      !deviceId ||
      !activeStatus?.connected ||
      !activeStatus.agent?.accessibility_enabled
    )
      return
    const controller = new AbortController()
    const firstRequest = window.setTimeout(
      () => void refreshUiTree(controller.signal),
      0,
    )
    const timer = window.setInterval(
      () => void refreshUiTree(controller.signal),
      UI_TREE_INTERVAL_MS,
    )
    return () => {
      controller.abort()
      window.clearTimeout(firstRequest)
      window.clearInterval(timer)
    }
  }, [
    activeStatus?.agent?.accessibility_enabled,
    activeStatus?.connected,
    deviceId,
    refreshUiTree,
  ])

  const action = useCallback(
    async (name: string, operation: () => Promise<unknown>) => {
      if (!deviceId || busy !== null) return
      const generation = deviceGeneration.current
      setBusy(name)
      setError(null)
      setNotice(null)
      try {
        const result = await operation()
        if (generation !== deviceGeneration.current) return
        if (result && typeof result === 'object' && 'macro' in result) {
          setDebug(result as AndroidDebugState)
        }
        setNotice(`${name} completed.`)
        await Promise.all([refreshStatus(), refreshDebug(), refreshUiTree()])
      } catch (caught) {
        if (generation === deviceGeneration.current) setError(message(caught))
      } finally {
        if (generation === deviceGeneration.current) setBusy(null)
      }
    },
    [busy, deviceId, refreshDebug, refreshStatus, refreshUiTree],
  )

  const selectUiNode = useCallback((nodeId: string | null) => {
    setSelectedUiNodeId(nodeId)
    const selected = uiTreeRef.current?.nodes.find((node) => node.node_id === nodeId)
    selectedUiNodeFingerprint.current = selected ? uiNodeFingerprint(selected) : null
  }, [])

  const tap = useCallback(
    async (x: number, y: number) => {
      if (!deviceId) return
      await action('Manual tap', () => androidApi.tap(deviceId, x, y))
    },
    [action, deviceId],
  )

  const gesture = useCallback(
    async (points: AndroidPointerPoint[]) => {
      if (!deviceId) return
      await action('Pointer gesture', () => androidApi.gesture(deviceId, points))
    },
    [action, deviceId],
  )

  const reconnectStream = useCallback(() => {
    setStreamFailed(false)
    setStreamNonce(Date.now())
  }, [])

  return {
    status: activeStatus,
    deviceId,
    debug: activeDebug,
    events: events.filter((event) => event.payload.device_id === deviceId),
    uiTree: activeUiTree,
    uiTreeError,
    uiTreeLoading,
    selectedUiNodeId,
    error,
    notice,
    busy,
    manualTapEnabled,
    selectedDetectionId,
    highlightedDetectionId,
    streamNonce,
    streamFailed,
    setManualTapEnabled,
    setSelectedDetectionId,
    setHighlightedDetectionId,
    setSelectedUiNodeId: selectUiNode,
    setStreamFailed,
    reconnectStream,
    refreshUiTree,
    tap,
    gesture,
    saveScreenshot: () =>
      action('Screenshot', () => androidApi.saveScreenshot(deviceId ?? '')),
    back: () => action('Back', () => androidApi.back(deviceId ?? '')),
    home: () => action('Home', () => androidApi.home(deviceId ?? '')),
    macroStart: () =>
      action('Macro start', () => androidApi.macroStart(deviceId ?? '')),
    macroPause: () =>
      action('Macro pause', () => androidApi.macroPause(deviceId ?? '')),
    macroStop: () => action('Macro stop', () => androidApi.macroStop(deviceId ?? '')),
    macroReset: () =>
      action('Macro reset', () => androidApi.macroReset(deviceId ?? '')),
    macroStep: () => action('Macro step', () => androidApi.macroStep(deviceId ?? '')),
  }
}

export type AndroidDebugController = ReturnType<typeof useAndroidDebug>
