import { useCallback, useEffect, useState } from 'react'
import type { AndroidDeviceSummary } from '../../types/android-debug'
import { androidApi } from './android-api'

const SUMMARY_INTERVAL_MS = 7_500

export function useAndroidDevices() {
  const [devices, setDevices] = useState<AndroidDeviceSummary[]>([])
  const [defaultDeviceId, setDefaultDeviceId] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async (signal?: AbortSignal) => {
    try {
      const response = await androidApi.devices(signal)
      setDevices(response.devices)
      setDefaultDeviceId(response.default_device_id)
      setError(null)
    } catch (caught) {
      if (signal?.aborted) return
      setError(
        caught instanceof Error ? caught.message : 'Could not load Android devices.',
      )
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const firstRequest = window.setTimeout(() => void refresh(controller.signal), 0)
    const timer = window.setInterval(
      () => void refresh(controller.signal),
      SUMMARY_INTERVAL_MS,
    )
    return () => {
      controller.abort()
      window.clearTimeout(firstRequest)
      window.clearInterval(timer)
    }
  }, [refresh])

  return { devices, defaultDeviceId, loading, error, refresh }
}
