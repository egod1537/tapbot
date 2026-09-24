import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api-client'
import type {
  LatestScreenPipelineResult,
  LiveVisionStatus,
  ScreenPipelineRunResult,
} from '../../types/vision'
import type { CameraStreamController } from '../camera/useCameraStream'
import { visionApi } from './vision-api'

export type PhoneDetectionStatus =
  'not-run' | 'running' | 'found' | 'not-found' | 'error'

export type CanonicalStatus = 'waiting' | 'transforming' | 'ready' | 'transform-failed'

const LIVE_RESULT_POLL_MS = 200
const LIVE_STATUS_POLL_MS = 750

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Screen pipeline failed.'
}

export function useRawCanonicalView(camera: CameraStreamController) {
  const [result, setResult] = useState<ScreenPipelineRunResult | null>(null)
  const [liveStatus, setLiveStatus] = useState<LiveVisionStatus | null>(null)
  const [phoneStatus, setPhoneStatus] = useState<PhoneDetectionStatus>('not-run')
  const [canonicalStatus, setCanonicalStatus] = useState<CanonicalStatus>('waiting')
  const [phoneError, setPhoneError] = useState<string | null>(null)
  const [canonicalError, setCanonicalError] = useState<string | null>(null)
  const [visionError, setVisionError] = useState<string | null>(null)
  const [pipelineRunning, setPipelineRunning] = useState(false)
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.5)
  const [selectedDetectionId, setSelectedDetectionId] = useState<string | null>(null)
  const [highlightedDetectionId, setHighlightedDetectionId] = useState<string | null>(
    null,
  )
  const [resultSourceId, setResultSourceId] = useState<string | null>(null)
  const requestGeneration = useRef(0)
  const latestAcceptedFrameId = useRef<number | null>(null)
  const sourceId = camera.sourceStatus?.source_id ?? null
  const sourceIdRef = useRef(sourceId)
  const previousSourceIdRef = useRef(sourceId)
  const isCurrentSource = resultSourceId === sourceId
  const isRunning = pipelineRunning && isCurrentSource

  useEffect(() => {
    sourceIdRef.current = sourceId
  }, [sourceId])

  const clear = useCallback(() => {
    requestGeneration.current += 1
    latestAcceptedFrameId.current = null
    setResult(null)
    setPhoneStatus('not-run')
    setCanonicalStatus('waiting')
    setPhoneError(null)
    setCanonicalError(null)
    setVisionError(null)
    setPipelineRunning(false)
    setSelectedDetectionId(null)
    setHighlightedDetectionId(null)
    setResultSourceId(null)
  }, [])

  useEffect(() => {
    if (previousSourceIdRef.current !== sourceId) {
      previousSourceIdRef.current = sourceId
      clear()
    }
  }, [clear, sourceId])

  const applyPipelineResult = useCallback(
    (pipelineResult: ScreenPipelineRunResult, resultSource: string | null) => {
      if (sourceIdRef.current !== resultSource) return
      if (pipelineResult.frame.frame_id !== pipelineResult.frame_id) {
        setResultSourceId(resultSource)
        setPhoneStatus('error')
        setCanonicalStatus('waiting')
        setPhoneError('Backend returned mismatched frame identifiers.')
        return
      }
      if (
        latestAcceptedFrameId.current !== null &&
        pipelineResult.frame_id < latestAcceptedFrameId.current
      ) {
        return
      }

      latestAcceptedFrameId.current = pipelineResult.frame_id
      setResultSourceId(resultSource)
      setResult(pipelineResult)
      setPhoneError(null)
      setCanonicalError(null)
      setVisionError(null)

      if (pipelineResult.failure_stage === 'phone_detection') {
        setPhoneStatus(pipelineResult.phone_detection.found ? 'error' : 'not-found')
        setPhoneError(
          pipelineResult.phone_detection.found ? pipelineResult.error : null,
        )
        setCanonicalStatus('waiting')
        return
      }

      setPhoneStatus(pipelineResult.phone_detection.found ? 'found' : 'not-found')
      if (pipelineResult.failure_stage === 'canonical_transform') {
        setCanonicalStatus('transform-failed')
        setCanonicalError(pipelineResult.error)
        return
      }
      if (pipelineResult.canonical === null) {
        setCanonicalStatus('transform-failed')
        setCanonicalError('The phone was found, but no canonical image was created.')
        return
      }

      setCanonicalStatus('ready')
      if (pipelineResult.failure_stage === 'ui_detection') {
        setVisionError(pipelineResult.error)
        return
      }
      setSelectedDetectionId(pipelineResult.detections[0]?.id ?? null)
    },
    [],
  )

  useEffect(() => {
    let active = true
    let timer: number | undefined
    let controller: AbortController | null = null

    const poll = async () => {
      controller = new AbortController()
      try {
        const latest: LatestScreenPipelineResult = await visionApi.liveResult(
          controller.signal,
        )
        if (!active || latest.source_id !== sourceIdRef.current) return
        if (latest.result !== null) {
          applyPipelineResult(latest.result, latest.source_id)
        } else if (latest.error) {
          setResultSourceId(latest.source_id)
          setPhoneStatus('error')
          setCanonicalStatus('waiting')
          setPhoneError(latest.error)
        }
      } catch (error) {
        if (
          error instanceof ApiError &&
          (error.status === 404 || error.code === 'REQUEST_ABORTED')
        ) {
          return
        }
        // Camera/backend status owns connection errors; keep the last vision result.
      } finally {
        if (active) timer = window.setTimeout(poll, LIVE_RESULT_POLL_MS)
      }
    }

    void poll()
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
      controller?.abort()
    }
  }, [applyPipelineResult])

  useEffect(() => {
    let active = true
    let timer: number | undefined
    let controller: AbortController | null = null

    const poll = async () => {
      controller = new AbortController()
      try {
        const status = await visionApi.liveStatus(controller.signal)
        if (active) setLiveStatus(status)
      } catch (error) {
        if (
          !(error instanceof ApiError && error.code === 'REQUEST_ABORTED') &&
          active
        ) {
          setLiveStatus(null)
        }
      } finally {
        if (active) timer = window.setTimeout(poll, LIVE_STATUS_POLL_MS)
      }
    }

    void poll()
    return () => {
      active = false
      if (timer !== undefined) window.clearTimeout(timer)
      controller?.abort()
    }
  }, [])

  const run = useCallback(async () => {
    if (!camera.frame || !camera.isConnected || isRunning) return
    const generation = requestGeneration.current + 1
    const requestedSourceId = sourceId
    requestGeneration.current = generation
    setResultSourceId(requestedSourceId)
    setPipelineRunning(true)
    setPhoneStatus('running')
    setCanonicalStatus('transforming')
    setPhoneError(null)
    setCanonicalError(null)
    setVisionError(null)

    try {
      const pipelineResult = await visionApi.runScreenPipeline({
        confidence_threshold: confidenceThreshold,
      })
      if (
        generation !== requestGeneration.current ||
        sourceIdRef.current !== requestedSourceId
      )
        return
      applyPipelineResult(pipelineResult, requestedSourceId)
    } catch (error) {
      if (
        generation !== requestGeneration.current ||
        sourceIdRef.current !== requestedSourceId
      )
        return
      setPhoneStatus('error')
      setCanonicalStatus('waiting')
      setPhoneError(errorMessage(error))
    } finally {
      if (
        generation === requestGeneration.current &&
        sourceIdRef.current === requestedSourceId
      ) {
        setPipelineRunning(false)
      }
    }
  }, [
    applyPipelineResult,
    camera.frame,
    camera.isConnected,
    confidenceThreshold,
    isRunning,
    sourceId,
  ])

  return {
    result: isCurrentSource ? result : null,
    liveStatus,
    phoneStatus: isCurrentSource ? phoneStatus : ('not-run' as const),
    canonicalStatus: isCurrentSource ? canonicalStatus : ('waiting' as const),
    phoneError: isCurrentSource ? phoneError : null,
    canonicalError: isCurrentSource ? canonicalError : null,
    visionError: isCurrentSource ? visionError : null,
    confidenceThreshold,
    setConfidenceThreshold,
    selectedDetectionId,
    setSelectedDetectionId,
    highlightedDetectionId,
    setHighlightedDetectionId,
    isRunning,
    run,
    clear,
  }
}

export type RawCanonicalController = ReturnType<typeof useRawCanonicalView>
