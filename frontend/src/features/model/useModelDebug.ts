import { useCallback, useEffect, useState } from 'react'
import { useSystemStatus } from '../../app/system-status'
import { ApiError } from '../../lib/api-client'
import type { ModelRunResult } from '../../types/model'
import type { VisionFrameMetadata } from '../../types/vision'
import { visionApi } from '../vision/vision-api'
import { modelApi } from './model-api'

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Model debug request failed.'
}

export function useModelDebug() {
  const system = useSystemStatus()
  const [frames, setFrames] = useState<VisionFrameMetadata[]>([])
  const [selectedFrameId, setSelectedFrameId] = useState<number | null>(null)
  const [result, setResult] = useState<ModelRunResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setLoading] = useState(true)
  const [isRunning, setRunning] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const savedFrames = await visionApi.frames()
      setFrames(savedFrames.frames)
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const initialRequest = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(initialRequest)
  }, [load])

  const run = async () => {
    if (isRunning) return
    setRunning(true)
    setError(null)
    try {
      const nextResult = await modelApi.run({
        frame_id: selectedFrameId,
        context: {
          source: 'model_debug_panel',
          manual_replay: true,
        },
      })
      setResult(nextResult)
      const savedFrames = await visionApi.frames()
      setFrames(savedFrames.frames)
      setSelectedFrameId(nextResult.frame.frame_id)
      system.refresh()
    } catch (requestError) {
      setError(errorMessage(requestError))
    } finally {
      setRunning(false)
    }
  }

  return {
    status: result?.model ?? system.modelStatus,
    frames,
    selectedFrameId,
    setSelectedFrameId,
    result,
    error: error ?? system.modelError,
    isLoading,
    isRunning,
    retry: () => void load(),
    run: () => void run(),
  }
}
