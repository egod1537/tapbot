import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { PropsWithChildren } from 'react'
import { ApiError } from '../lib/api-client'
import type { ModelStatus } from '../types/model'
import type { RobotStatus } from '../types/robot'
import type { BackendConnectionState, BackendSystemStatus } from '../types/system'
import { modelApi } from '../features/model/model-api'
import { robotApi } from '../features/robot/robot-api'
import { systemApi } from '../features/system/system-api'
import { SystemStatusContext } from './system-status'

const STATUS_INTERVAL_MS = 2_000

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Status request failed.'
}

export function SystemStatusProvider({ children }: PropsWithChildren) {
  const [backend, setBackend] = useState<BackendSystemStatus | null>(null)
  const [backendState, setBackendState] = useState<BackendConnectionState>('connecting')
  const [backendError, setBackendError] = useState<string | null>(null)
  const [robotStatus, setRobotStatus] = useState<RobotStatus | null>(null)
  const [robotError, setRobotError] = useState<string | null>(null)
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null)
  const [modelError, setModelError] = useState<string | null>(null)
  const [isEmergencyStopping, setEmergencyStopping] = useState(false)
  const [emergencyError, setEmergencyError] = useState<string | null>(null)
  const requestInFlight = useRef(false)

  const refresh = useCallback(async () => {
    if (requestInFlight.current) return
    requestInFlight.current = true
    const [backendResult, robotResult, modelResult] = await Promise.allSettled([
      systemApi.status(),
      robotApi.status(),
      modelApi.status(),
    ])

    if (backendResult.status === 'fulfilled') {
      setBackend(backendResult.value)
      setBackendState('online')
      setBackendError(null)
    } else {
      setBackendState('offline')
      setBackendError(errorMessage(backendResult.reason))
    }

    if (robotResult.status === 'fulfilled') {
      setRobotStatus(robotResult.value)
      setRobotError(
        robotResult.value.connected ? null : 'Robot controller is disconnected.',
      )
    } else {
      setRobotError(errorMessage(robotResult.reason))
    }

    if (modelResult.status === 'fulfilled') {
      setModelStatus(modelResult.value)
      setModelError(modelResult.value.connected ? null : 'Local model is unavailable.')
    } else {
      setModelError(errorMessage(modelResult.reason))
    }
    requestInFlight.current = false
  }, [])

  useEffect(() => {
    const firstRequest = window.setTimeout(() => void refresh(), 0)
    const interval = window.setInterval(() => void refresh(), STATUS_INTERVAL_MS)
    return () => {
      window.clearTimeout(firstRequest)
      window.clearInterval(interval)
    }
  }, [refresh])

  const emergencyStop = useCallback(async () => {
    if (isEmergencyStopping) return
    setEmergencyStopping(true)
    setEmergencyError(null)
    try {
      await robotApi.emergencyStop()
    } catch (error) {
      setEmergencyError(errorMessage(error))
    } finally {
      setEmergencyStopping(false)
      await refresh()
    }
  }, [isEmergencyStopping, refresh])

  const cameraError =
    backendState === 'offline'
      ? 'Backend disconnected; camera status is unavailable.'
      : (backend?.camera_error ??
        (backend && !backend.camera_opened ? 'Camera service is unavailable.' : null))
  const calibrationMissing = backendState === 'online' && !backend?.calibration_profile

  const value = useMemo(
    () => ({
      backend,
      backendState,
      backendError,
      robotStatus,
      robotError,
      modelStatus,
      modelError,
      cameraError,
      calibrationMissing,
      isEmergencyStopping,
      emergencyError,
      refresh: () => void refresh(),
      emergencyStop: () => void emergencyStop(),
    }),
    [
      backend,
      backendError,
      backendState,
      calibrationMissing,
      cameraError,
      emergencyError,
      emergencyStop,
      isEmergencyStopping,
      modelError,
      modelStatus,
      refresh,
      robotError,
      robotStatus,
    ],
  )

  return (
    <SystemStatusContext.Provider value={value}>
      {children}
    </SystemStatusContext.Provider>
  )
}
