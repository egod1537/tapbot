import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api-client'
import type { ScreenPipelineRunResult } from '../../types/vision'
import type { CameraStreamController } from '../camera/useCameraStream'
import { visionApi } from './vision-api'

export type PhoneDetectionStatus =
  'not-run' | 'running' | 'found' | 'not-found' | 'error'

export type CanonicalStatus = 'waiting' | 'transforming' | 'ready' | 'transform-failed'

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Screen pipeline failed.'
}

export function useRawCanonicalView(camera: CameraStreamController) {
  const [result, setResult] = useState<ScreenPipelineRunResult | null>(null)
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

  const run = useCallback(async () => {
    if (!camera.frame || !camera.isConnected || isRunning) return
    const generation = requestGeneration.current + 1
    const requestedSourceId = sourceId
    requestGeneration.current = generation
    setResultSourceId(requestedSourceId)
    setPipelineRunning(true)
    setResult(null)
    setPhoneStatus('running')
    setCanonicalStatus('transforming')
    setPhoneError(null)
    setCanonicalError(null)
    setVisionError(null)
    setSelectedDetectionId(null)
    setHighlightedDetectionId(null)

    try {
      const pipelineResult = await visionApi.runScreenPipeline({
        confidence_threshold: confidenceThreshold,
      })
      if (
        generation !== requestGeneration.current ||
        sourceIdRef.current !== requestedSourceId
      )
        return

      if (pipelineResult.frame.frame_id !== pipelineResult.frame_id) {
        setPhoneStatus('error')
        setCanonicalStatus('waiting')
        setPhoneError('Backend returned mismatched frame identifiers.')
        return
      }

      setResult(pipelineResult)
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
  }, [camera.frame, camera.isConnected, confidenceThreshold, isRunning, sourceId])

  return {
    result: isCurrentSource ? result : null,
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
