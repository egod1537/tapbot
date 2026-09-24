import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  CameraFrame,
  CameraSourceDescriptor,
  CameraSourceStatus,
} from '../../types/camera'
import {
  fetchCameraFrame,
  fetchCameraSources,
  fetchCameraStatus,
  reconnectCameraSource,
  resetMockCameraGraph,
  selectCameraSource,
} from './camera-api'

const FRAME_INTERVAL_MS = 250
const FRAME_TIMEOUT_MS = 5_000
const SOURCE_STATUS_INTERVAL_MS = 1_000

export type CameraSourceActivity =
  'switching' | 'refreshing' | 'reconnecting' | 'resetting'

function cameraErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Camera frame is unavailable.'
}

export function useCameraStream() {
  const [frame, setFrame] = useState<CameraFrame | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fps, setFps] = useState<number | null>(null)
  const [sources, setSources] = useState<CameraSourceDescriptor[]>([])
  const [sourceStatus, setSourceStatus] = useState<CameraSourceStatus | null>(null)
  const [sourceError, setSourceError] = useState<string | null>(null)
  const [sourceActivity, setSourceActivity] = useState<CameraSourceActivity | null>(
    null,
  )
  const isSourceBusy = sourceActivity !== null
  const currentUrl = useRef<string | null>(null)
  const currentBlob = useRef<Blob | null>(null)
  const lastFrameId = useRef<number | null>(null)
  const lastFrameAt = useRef<number | null>(null)
  const measuredFps = useRef<number | null>(null)
  const sourceGeneration = useRef(0)

  const resetFrame = useCallback(() => {
    sourceGeneration.current += 1
    if (currentUrl.current) URL.revokeObjectURL(currentUrl.current)
    currentUrl.current = null
    currentBlob.current = null
    lastFrameId.current = null
    lastFrameAt.current = null
    measuredFps.current = null
    setFrame(null)
    setFps(null)
  }, [])

  const refreshSourceState = useCallback(
    async (signal?: AbortSignal, discover = false) => {
      const [sourceList, status] = await Promise.all([
        fetchCameraSources(signal, discover),
        fetchCameraStatus(signal),
      ])
      setSources(sourceList.sources)
      setSourceStatus(status)
      setSourceError(null)
    },
    [],
  )

  useEffect(() => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => {
      void refreshSourceState(controller.signal).catch(
        (sourceRequestError: unknown) => {
          if (!controller.signal.aborted) {
            setSourceError(cameraErrorMessage(sourceRequestError))
          }
        },
      )
    }, 0)
    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [refreshSourceState])

  useEffect(() => {
    if (isSourceBusy) return

    let active = true
    let timer: number | undefined
    const controller = new AbortController()
    const pollStatus = async () => {
      try {
        const status = await fetchCameraStatus(controller.signal)
        if (active) {
          setSourceStatus(status)
          setSourceError(status.error)
        }
      } catch (statusError) {
        if (active && !controller.signal.aborted) {
          setSourceError(cameraErrorMessage(statusError))
        }
      } finally {
        if (active) {
          timer = window.setTimeout(() => void pollStatus(), SOURCE_STATUS_INTERVAL_MS)
        }
      }
    }
    void pollStatus()
    return () => {
      active = false
      controller.abort()
      if (timer !== undefined) window.clearTimeout(timer)
    }
  }, [isSourceBusy])

  useEffect(() => {
    let active = true
    let pollTimer: number | undefined
    let requestTimeout: number | undefined
    let controller: AbortController | undefined

    const poll = async () => {
      const requestGeneration = sourceGeneration.current
      controller = new AbortController()
      requestTimeout = window.setTimeout(() => controller?.abort(), FRAME_TIMEOUT_MS)

      try {
        const response = await fetchCameraFrame(controller.signal)
        if (!active) return
        if (requestGeneration !== sourceGeneration.current) return
        if (response.frameId === lastFrameId.current) {
          setError(null)
          return
        }

        const now = performance.now()
        if (lastFrameAt.current !== null) {
          const instantaneousFps = 1_000 / (now - lastFrameAt.current)
          measuredFps.current =
            measuredFps.current === null
              ? instantaneousFps
              : measuredFps.current * 0.75 + instantaneousFps * 0.25
          setFps(measuredFps.current)
        }
        lastFrameId.current = response.frameId
        lastFrameAt.current = now

        const objectUrl = URL.createObjectURL(response.blob)
        const previousUrl = currentUrl.current
        currentUrl.current = objectUrl
        currentBlob.current = response.blob
        setFrame({ ...response, objectUrl })
        setError(null)
        if (previousUrl) {
          window.setTimeout(() => URL.revokeObjectURL(previousUrl), 0)
        }
      } catch (requestError) {
        if (active && !controller.signal.aborted) {
          setError(cameraErrorMessage(requestError))
          setFps(null)
          lastFrameAt.current = null
          measuredFps.current = null
        } else if (active && controller.signal.aborted) {
          setError('Camera request timed out.')
          setFps(null)
        }
      } finally {
        if (requestTimeout !== undefined) window.clearTimeout(requestTimeout)
        if (active) pollTimer = window.setTimeout(poll, FRAME_INTERVAL_MS)
      }
    }

    pollTimer = window.setTimeout(() => void poll(), 0)

    return () => {
      active = false
      if (pollTimer !== undefined) window.clearTimeout(pollTimer)
      if (requestTimeout !== undefined) window.clearTimeout(requestTimeout)
      controller?.abort()
      if (currentUrl.current) URL.revokeObjectURL(currentUrl.current)
      currentUrl.current = null
      currentBlob.current = null
      lastFrameId.current = null
    }
  }, [])

  const saveScreenshot = useCallback((): number | null => {
    if (!frame || !currentBlob.current) return null
    const timestamp = frame.capturedAt.replaceAll(':', '-').replaceAll('.', '-')
    const link = document.createElement('a')
    link.href = frame.objectUrl
    link.download = `tapbot-frame-${frame.frameId}-${timestamp || 'capture'}.jpg`
    document.body.appendChild(link)
    link.click()
    link.remove()
    return frame.frameId
  }, [frame])

  const chooseSource = useCallback(
    async (sourceId: string) => {
      if (!sourceId || sourceId === sourceStatus?.source_id) return
      setSourceActivity('switching')
      setSourceError(null)
      resetFrame()
      try {
        await selectCameraSource(sourceId)
        await refreshSourceState()
        setError(null)
      } catch (sourceRequestError) {
        const message = cameraErrorMessage(sourceRequestError)
        setSourceError(message)
        setError(message)
        try {
          setSourceStatus(await fetchCameraStatus())
        } catch {
          // Preserve the source selection error as the actionable message.
        }
      } finally {
        setSourceActivity(null)
      }
    },
    [refreshSourceState, resetFrame, sourceStatus?.source_id],
  )

  const reconnect = useCallback(async () => {
    setSourceActivity('reconnecting')
    setSourceError(null)
    resetFrame()
    try {
      const status = await reconnectCameraSource()
      setSourceStatus(status)
      setError(null)
      await refreshSourceState()
    } catch (sourceRequestError) {
      const message = cameraErrorMessage(sourceRequestError)
      setSourceError(message)
      setError(message)
      try {
        setSourceStatus(await fetchCameraStatus())
      } catch {
        // Preserve the reconnect error as the actionable message.
      }
    } finally {
      setSourceActivity(null)
    }
  }, [refreshSourceState, resetFrame])

  const refreshSources = useCallback(async () => {
    setSourceActivity('refreshing')
    setSourceError(null)
    try {
      await refreshSourceState(undefined, true)
    } catch (sourceRequestError) {
      setSourceError(cameraErrorMessage(sourceRequestError))
    } finally {
      setSourceActivity(null)
    }
  }, [refreshSourceState])

  const resetGraph = useCallback(async () => {
    setSourceActivity('resetting')
    setSourceError(null)
    resetFrame()
    try {
      const status = await resetMockCameraGraph()
      setSourceStatus(status)
      setError(null)
      await refreshSourceState()
    } catch (sourceRequestError) {
      const message = cameraErrorMessage(sourceRequestError)
      setSourceError(message)
      setError(message)
      try {
        setSourceStatus(await fetchCameraStatus())
      } catch {
        // Preserve the reset error as the actionable message.
      }
    } finally {
      setSourceActivity(null)
    }
  }, [refreshSourceState, resetFrame])

  return {
    frame,
    error,
    fps,
    isConnected: frame !== null && error === null,
    sources,
    sourceStatus,
    sourceError,
    isSourceBusy,
    sourceActivity,
    chooseSource,
    refreshSources,
    reconnect,
    resetGraph,
    invalidateFrame: resetFrame,
    retry: () => void reconnect(),
    saveScreenshot,
  }
}

export type CameraStreamController = ReturnType<typeof useCameraStream>
