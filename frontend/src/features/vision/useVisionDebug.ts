import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api-client'
import type {
  VisionCapabilities,
  VisionFrameMetadata,
  VisionRunResult,
} from '../../types/vision'
import { visionApi } from './vision-api'

const DEFAULT_CONFIDENCE_THRESHOLD = 0.5

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Vision request failed.'
}

export function useVisionDebug() {
  const [capabilities, setCapabilities] = useState<VisionCapabilities | null>(null)
  const [frames, setFrames] = useState<VisionFrameMetadata[]>([])
  const [selectedFrameId, setSelectedFrameId] = useState<number | null>(null)
  const [enabledDetectorTypes, setEnabledDetectorTypes] = useState<string[]>([])
  const [confidenceThreshold, setConfidenceThreshold] = useState(
    DEFAULT_CONFIDENCE_THRESHOLD,
  )
  const [currentResult, setCurrentResult] = useState<VisionRunResult | null>(null)
  const [previousResult, setPreviousResult] = useState<VisionRunResult | null>(null)
  const [selectedDetectionId, setSelectedDetectionId] = useState<string | null>(null)
  const [highlightedDetectionId, setHighlightedDetectionId] = useState<string | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setLoading] = useState(true)
  const [isRunning, setRunning] = useState(false)
  const [isSaving, setSaving] = useState(false)
  const currentResultRef = useRef<VisionRunResult | null>(null)

  const executeRun = useCallback(
    async (
      frameId: number,
      detectorTypes: string[],
      threshold: number,
      retainCurrent: boolean,
    ) => {
      setRunning(true)
      setError(null)
      try {
        const result = await visionApi.run({
          frame_id: frameId,
          detector_types: detectorTypes,
          confidence_threshold: threshold,
        })
        if (retainCurrent && currentResultRef.current) {
          setPreviousResult(currentResultRef.current)
        }
        currentResultRef.current = result
        setCurrentResult(result)
        setSelectedDetectionId(result.detections[0]?.id ?? null)
        setHighlightedDetectionId(null)
      } catch (requestError) {
        setError(errorMessage(requestError))
      } finally {
        setRunning(false)
      }
    },
    [],
  )

  const initialize = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [capabilityResult, frameResult] = await Promise.all([
        visionApi.capabilities(),
        visionApi.frames(),
      ])
      const detectorTypes = capabilityResult.detectors.map((detector) => detector.type)
      setCapabilities(capabilityResult)
      setEnabledDetectorTypes(detectorTypes)
      setFrames(frameResult.frames)
      setSelectedFrameId(frameResult.frames[0]?.frame_id ?? null)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const initialRequest = window.setTimeout(() => void initialize(), 0)
    return () => window.clearTimeout(initialRequest)
  }, [initialize])

  const saveFrame = async (): Promise<number | null> => {
    if (isSaving || isRunning) return null
    setSaving(true)
    setError(null)
    try {
      const saved = await visionApi.saveFrame()
      setFrames((current) =>
        [
          saved.frame,
          ...current.filter((frame) => frame.frame_id !== saved.frame.frame_id),
        ].slice(0, capabilities?.max_saved_frames ?? 8),
      )
      setSelectedFrameId(saved.frame.frame_id)
      return saved.frame.frame_id
    } catch (requestError) {
      setError(errorMessage(requestError))
      return null
    } finally {
      setSaving(false)
    }
  }

  const saveAndRun = async () => {
    if (isSaving || isRunning) return
    setSaving(true)
    setError(null)
    try {
      const saved = await visionApi.saveFrame()
      setFrames((current) =>
        [
          saved.frame,
          ...current.filter((frame) => frame.frame_id !== saved.frame.frame_id),
        ].slice(0, capabilities?.max_saved_frames ?? 8),
      )
      setSelectedFrameId(saved.frame.frame_id)
      await executeRun(
        saved.frame.frame_id,
        enabledDetectorTypes,
        confidenceThreshold,
        true,
      )
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setSaving(false)
    }
  }

  const runSelected = () => {
    if (selectedFrameId === null || isRunning || isSaving) return
    void executeRun(selectedFrameId, enabledDetectorTypes, confidenceThreshold, true)
  }

  return {
    capabilities,
    frames,
    selectedFrameId,
    setSelectedFrameId,
    enabledDetectorTypes,
    toggleDetector: (detectorType: string) => {
      setEnabledDetectorTypes((current) =>
        current.includes(detectorType)
          ? current.filter((item) => item !== detectorType)
          : [...current, detectorType],
      )
    },
    confidenceThreshold,
    setConfidenceThreshold,
    currentResult,
    previousResult,
    clearPrevious: () => setPreviousResult(null),
    selectedDetectionId,
    setSelectedDetectionId,
    highlightedDetectionId,
    setHighlightedDetectionId,
    error,
    isLoading,
    isRunning,
    isSaving,
    retry: () => void initialize(),
    saveFrame: () => void saveFrame(),
    saveAndRun: () => void saveAndRun(),
    runSelected,
  }
}

export type VisionDebugController = ReturnType<typeof useVisionDebug>
