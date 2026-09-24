import { useCallback, useEffect, useRef, useState } from 'react'
import type { CameraFrame } from '../../types/camera'
import { fetchCameraFrame } from './camera-api'

const FRAME_INTERVAL_MS = 250
const FRAME_TIMEOUT_MS = 5_000

function cameraErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return 'Camera frame is unavailable.'
}

export function useCameraStream() {
  const [frame, setFrame] = useState<CameraFrame | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [fps, setFps] = useState<number | null>(null)
  const currentUrl = useRef<string | null>(null)
  const currentBlob = useRef<Blob | null>(null)
  const lastFrameId = useRef<number | null>(null)
  const lastFrameAt = useRef<number | null>(null)
  const measuredFps = useRef<number | null>(null)

  useEffect(() => {
    let active = true
    let pollTimer: number | undefined
    let requestTimeout: number | undefined
    let controller: AbortController | undefined

    const poll = async () => {
      controller = new AbortController()
      requestTimeout = window.setTimeout(() => controller?.abort(), FRAME_TIMEOUT_MS)

      try {
        const response = await fetchCameraFrame(controller.signal)
        if (!active) return
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

  return {
    frame,
    error,
    fps,
    isConnected: frame !== null && error === null,
    retry: () => setError(null),
    saveScreenshot,
  }
}

export type CameraStreamController = ReturnType<typeof useCameraStream>
