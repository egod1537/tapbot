import { useCallback, useRef, useState } from 'react'
import { useSystemStatus } from '../../app/system-status'
import { ApiError } from '../../lib/api-client'
import type {
  RobotCommandName,
  RobotCommandResponse,
  RobotCommandResult,
  RobotCoordinates,
} from '../../types/robot'
import { robotApi } from './robot-api'

export interface RobotToast {
  id: number
  tone: 'success' | 'error'
  title: string
  message: string
}

type CommandCall = () => Promise<RobotCommandResponse>

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'An unexpected robot error occurred.'
}

export function useRobotControl() {
  const system = useSystemStatus()
  const [pendingCommand, setPendingCommand] = useState<RobotCommandName | null>(null)
  const [isStopping, setStopping] = useState(false)
  const [lastResult, setLastResult] = useState<RobotCommandResult | null>(null)
  const [toast, setToast] = useState<RobotToast | null>(null)
  const toastId = useRef(0)

  const showToast = useCallback(
    (tone: RobotToast['tone'], title: string, message: string) => {
      const id = ++toastId.current
      setToast({ id, tone, title, message })
      window.setTimeout(() => {
        setToast((current) => (current?.id === id ? null : current))
      }, 4_500)
    },
    [],
  )

  const runCommand = useCallback(
    async (name: RobotCommandName, call: CommandCall, emergency = false) => {
      const startedAt = performance.now()
      if (emergency) setStopping(true)
      else setPendingCommand(name)

      try {
        await call()
        const latencyMs = Math.round(performance.now() - startedAt)
        setLastResult({
          name,
          succeeded: true,
          latencyMs,
          completedAt: new Date(),
        })
        showToast(
          'success',
          `${name} completed`,
          `Backend responded in ${latencyMs} ms.`,
        )
      } catch (error) {
        const latencyMs = Math.round(performance.now() - startedAt)
        const message = errorMessage(error)
        setLastResult({
          name,
          succeeded: false,
          latencyMs,
          completedAt: new Date(),
        })
        const title =
          error instanceof ApiError && error.code === 'REQUEST_TIMEOUT'
            ? 'Robot timeout'
            : `${name} failed`
        showToast('error', title, message)
      } finally {
        if (emergency) setStopping(false)
        else setPendingCommand(null)
        system.refresh()
      }
    },
    [showToast, system],
  )

  return {
    status: system.robotStatus,
    statusError:
      system.robotError ??
      (system.backendState === 'offline' ? system.backendError : null),
    pendingCommand,
    isStopping,
    lastResult,
    toast,
    dismissToast: () => setToast(null),
    refreshStatus: system.refresh,
    move: (coordinates: RobotCoordinates) =>
      void runCommand('Move', () => robotApi.move(coordinates)),
    tap: (coordinates: RobotCoordinates) =>
      void runCommand('Tap', () => robotApi.tap(coordinates)),
    home: () => void runCommand('Home', robotApi.home),
    penUp: () => void runCommand('Pen up', robotApi.penUp),
    penDown: () => void runCommand('Pen down', robotApi.penDown),
    emergencyStop: () =>
      void runCommand('Emergency stop', robotApi.emergencyStop, true),
  }
}
