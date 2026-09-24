import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../../lib/api-client'
import type {
  ConsoleEntry,
  GcodeCapabilities,
  GcodeCommandResponse,
} from '../../types/gcode'
import { robotApi } from '../robot/robot-api'
import { gcodeApi } from './gcode-api'

const COMMAND_HISTORY_KEY = 'tapbot.gcode.command-history'
const MAX_COMMAND_HISTORY = 50
const MAX_OUTPUT_ENTRIES = 100

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Unknown console error.'
}

function storedCommandHistory(): string[] {
  try {
    const value = JSON.parse(
      localStorage.getItem(COMMAND_HISTORY_KEY) ?? '[]',
    ) as unknown
    if (!Array.isArray(value)) return []
    return value.filter((item): item is string => typeof item === 'string').slice(-50)
  } catch {
    return []
  }
}

export function useGcodeConsole() {
  const [capabilities, setCapabilities] = useState<GcodeCapabilities | null>(null)
  const [capabilityError, setCapabilityError] = useState<string | null>(null)
  const [command, setCommand] = useState('')
  const [commandHistory, setCommandHistory] = useState<string[]>(storedCommandHistory)
  const [historyCursor, setHistoryCursor] = useState<number | null>(null)
  const [entries, setEntries] = useState<ConsoleEntry[]>([])
  const [isSending, setSending] = useState(false)
  const [isStopping, setStopping] = useState(false)
  const [copied, setCopied] = useState(false)
  const entryIds = useRef(0)
  const draftCommand = useRef('')

  const refreshCapabilities = useCallback(async () => {
    try {
      const result = await gcodeApi.capabilities()
      setCapabilities(result)
      setCapabilityError(null)
    } catch (error) {
      setCapabilities(null)
      setCapabilityError(errorMessage(error))
    }
  }, [])

  useEffect(() => {
    const initialRequest = window.setTimeout(() => {
      void refreshCapabilities()
    }, 0)
    return () => window.clearTimeout(initialRequest)
  }, [refreshCapabilities])

  const appendEntry = useCallback((entry: Omit<ConsoleEntry, 'id'>) => {
    const value = { ...entry, id: ++entryIds.current }
    setEntries((current) => [...current, value].slice(-MAX_OUTPUT_ENTRIES))
  }, [])

  const rememberCommand = (value: string) => {
    setCommandHistory((current) => {
      const next = [...current.filter((item) => item !== value), value].slice(
        -MAX_COMMAND_HISTORY,
      )
      localStorage.setItem(COMMAND_HISTORY_KEY, JSON.stringify(next))
      return next
    })
  }

  const send = async () => {
    const value = command.trim()
    if (!value || isSending || !capabilities?.available) return
    const startedAt = performance.now()
    setSending(true)
    setHistoryCursor(null)
    rememberCommand(value)
    try {
      const result: GcodeCommandResponse = await gcodeApi.send(value)
      appendEntry({
        command: result.command,
        response: result.response,
        status: 'ok',
        timestamp: new Date(),
        latencyMs: Math.round(performance.now() - startedAt),
      })
      setCommand('')
    } catch (error) {
      appendEntry({
        command: value,
        response: [errorMessage(error)],
        status: 'error',
        timestamp: new Date(),
        latencyMs: Math.round(performance.now() - startedAt),
      })
    } finally {
      setSending(false)
    }
  }

  const emergencyStop = async () => {
    if (isStopping) return
    const startedAt = performance.now()
    setStopping(true)
    try {
      await robotApi.emergencyStop()
      appendEntry({
        command: 'EMERGENCY STOP',
        response: ['Dedicated stop endpoint acknowledged.'],
        status: 'stopped',
        timestamp: new Date(),
        latencyMs: Math.round(performance.now() - startedAt),
      })
    } catch (error) {
      appendEntry({
        command: 'EMERGENCY STOP',
        response: [errorMessage(error)],
        status: 'error',
        timestamp: new Date(),
        latencyMs: Math.round(performance.now() - startedAt),
      })
    } finally {
      setStopping(false)
    }
  }

  const navigateHistory = (direction: 'previous' | 'next') => {
    if (commandHistory.length === 0) return
    if (direction === 'previous') {
      const nextIndex =
        historyCursor === null
          ? commandHistory.length - 1
          : Math.max(0, historyCursor - 1)
      if (historyCursor === null) draftCommand.current = command
      setHistoryCursor(nextIndex)
      setCommand(commandHistory[nextIndex] ?? '')
      return
    }
    if (historyCursor === null) return
    const nextIndex = historyCursor + 1
    if (nextIndex >= commandHistory.length) {
      setHistoryCursor(null)
      setCommand(draftCommand.current)
    } else {
      setHistoryCursor(nextIndex)
      setCommand(commandHistory[nextIndex] ?? '')
    }
  }

  const copyOutput = async () => {
    if (entries.length === 0) return
    const text = entries
      .flatMap((entry) => [
        `[${entry.timestamp.toISOString()}] > ${entry.command}`,
        ...entry.response.map((line) => `< ${line}`),
        `[${entry.status}] ${entry.latencyMs.toString()} ms`,
      ])
      .join('\n')
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1_500)
    } catch {
      setCopied(false)
    }
  }

  return {
    capabilities,
    capabilityError,
    command,
    setCommand: (value: string) => {
      setCommand(value.replace(/[\r\n]/g, ''))
      setHistoryCursor(null)
    },
    entries,
    isSending,
    isStopping,
    copied,
    send: () => void send(),
    emergencyStop: () => void emergencyStop(),
    navigateHistory,
    selectPreset: (value: string) => {
      setCommand(value)
      setHistoryCursor(null)
    },
    clear: () => setEntries([]),
    copyOutput: () => void copyOutput(),
    refreshCapabilities: () => void refreshCapabilities(),
  }
}
