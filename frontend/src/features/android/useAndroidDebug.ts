import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api-client'
import type { AndroidDebugState, AndroidProxyStatus } from '../../types/android-debug'
import type { TimelineEvent } from '../../types/timeline'
import { timelineApi } from '../timeline/timeline-api'
import { androidApi } from './android-api'

const STATUS_INTERVAL_MS = 2_000
const DEBUG_INTERVAL_MS = 1_000
const VISION_INTERVAL_MS = 1_500

function message(error: unknown): string {
  if (error instanceof ApiError || error instanceof Error) return error.message
  return 'Android debug request failed.'
}

export function useAndroidDebug() {
  const [status, setStatus] = useState<AndroidProxyStatus | null>(null)
  const [debug, setDebug] = useState<AndroidDebugState | null>(null)
  const [events, setEvents] = useState<TimelineEvent[]>([])
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

  const refreshStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      const next = await androidApi.status(signal)
      setStatus(next)
      setError(next.error)
    } catch (caught) {
      if (signal?.aborted) return
      setError(message(caught))
    }
  }, [])

  const refreshDebug = useCallback(async (signal?: AbortSignal) => {
    try {
      const [nextDebug, log] = await Promise.all([
        androidApi.debugState(signal),
        timelineApi.entries(),
      ])
      setDebug(nextDebug)
      setEvents(log.entries.slice(-40).reverse())
    } catch (caught) {
      if (signal?.aborted) return
      if (caught instanceof ApiError && caught.status === 503) return
      setError(message(caught))
    }
  }, [])

  useEffect(() => {
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
  }, [refreshDebug, refreshStatus])

  useEffect(() => {
    if (!status?.connected || !status.agent?.capture_ready) return
    let cancelled = false
    const run = async () => {
      if (visionInFlight.current || cancelled) return
      visionInFlight.current = true
      try {
        const next = await androidApi.runVision()
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
      window.clearInterval(timer)
    }
  }, [status?.agent?.capture_ready, status?.connected])

  const action = useCallback(
    async (name: string, operation: () => Promise<unknown>) => {
      if (busy !== null) return
      setBusy(name)
      setError(null)
      setNotice(null)
      try {
        const result = await operation()
        if (result && typeof result === 'object' && 'macro' in result) {
          setDebug(result as AndroidDebugState)
        }
        setNotice(`${name} completed.`)
        await Promise.all([refreshStatus(), refreshDebug()])
      } catch (caught) {
        setError(message(caught))
      } finally {
        setBusy(null)
      }
    },
    [busy, refreshDebug, refreshStatus],
  )

  const tap = useCallback(
    async (x: number, y: number) => {
      await action('Manual tap', () => androidApi.tap(x, y))
    },
    [action],
  )

  const reconnectStream = useCallback(() => {
    setStreamFailed(false)
    setStreamNonce(Date.now())
  }, [])

  return {
    status,
    debug,
    events,
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
    setStreamFailed,
    reconnectStream,
    tap,
    saveScreenshot: () => action('Screenshot', androidApi.saveScreenshot),
    back: () => action('Back', androidApi.back),
    home: () => action('Home', androidApi.home),
    macroStart: () => action('Macro start', androidApi.macroStart),
    macroPause: () => action('Macro pause', androidApi.macroPause),
    macroStop: () => action('Macro stop', androidApi.macroStop),
    macroReset: () => action('Macro reset', androidApi.macroReset),
    macroStep: () => action('Macro step', androidApi.macroStep),
  }
}

export type AndroidDebugController = ReturnType<typeof useAndroidDebug>
