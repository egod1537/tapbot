import { Callout, Spinner } from '@blueprintjs/core'
import { useEffect } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { AndroidDebugWorkspace } from '../features/android/AndroidDebugWorkspace'
import { useAndroidDebug } from '../features/android/useAndroidDebug'
import { useAndroidDevices } from '../features/android/useAndroidDevices'

export function DebugPage() {
  const { deviceId: routeDeviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const deviceList = useAndroidDevices()
  const selectedDeviceId =
    routeDeviceId && deviceList.devices.some((device) => device.id === routeDeviceId)
      ? routeDeviceId
      : null
  const controller = useAndroidDebug(selectedDeviceId)

  useEffect(() => {
    if (deviceList.loading || selectedDeviceId || deviceList.devices.length === 0)
      return
    const next =
      deviceList.defaultDeviceId ??
      deviceList.devices.find((device) => device.connected)?.id ??
      deviceList.devices[0]?.id
    if (next) {
      void navigate(`/debug/android/${encodeURIComponent(next)}`, { replace: true })
    }
  }, [
    deviceList.defaultDeviceId,
    deviceList.devices,
    deviceList.loading,
    navigate,
    selectedDeviceId,
  ])

  if (deviceList.loading && deviceList.devices.length === 0) {
    return <Spinner size={36} />
  }

  if (deviceList.error && deviceList.devices.length === 0) {
    return <Callout intent="danger">{deviceList.error}</Callout>
  }

  if (deviceList.devices.length === 0) {
    return (
      <Callout intent="warning" title="No Android devices configured">
        Set TAPBOT_ANDROID_DEVICES_CONFIG or the legacy Android Agent environment
        variables on the backend.
      </Callout>
    )
  }

  return (
    <div className="vision-workspace-page">
      <AndroidDebugWorkspace
        controller={controller}
        devices={deviceList.devices}
        onDeviceChange={(deviceId) => {
          void navigate(`/debug/android/${encodeURIComponent(deviceId)}`)
        }}
      />
    </div>
  )
}
