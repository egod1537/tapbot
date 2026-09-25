import { apiClient } from '../../lib/api-client'
import { apiUrl } from '../../lib/config'
import type {
  AndroidDebugState,
  AndroidDevicesResponse,
  AndroidPrimitiveResult,
  AndroidPointerPoint,
  AndroidProxyStatus,
  AndroidScreenshotSaveResult,
  AndroidUiTree,
} from '../../types/android-debug'

export const androidApi = {
  devices: (signal?: AbortSignal) =>
    apiClient.get<AndroidDevicesResponse>('android/devices', { signal }),
  status: (deviceId: string, signal?: AbortSignal) =>
    apiClient.get<AndroidProxyStatus>(
      `android/${encodeURIComponent(deviceId)}/status`,
      {
        signal,
      },
    ),
  debugState: (deviceId: string, signal?: AbortSignal) =>
    apiClient.get<AndroidDebugState>(
      `android/${encodeURIComponent(deviceId)}/debug/state`,
      { signal },
    ),
  uiTree: (deviceId: string, signal?: AbortSignal) =>
    apiClient.get<AndroidUiTree>(`android/${encodeURIComponent(deviceId)}/ui-tree`, {
      signal,
    }),
  runVision: (deviceId: string, signal?: AbortSignal) =>
    apiClient.post<AndroidDebugState>(
      `android/${encodeURIComponent(deviceId)}/vision/run`,
      undefined,
      { signal },
    ),
  saveScreenshot: (deviceId: string) =>
    apiClient.post<AndroidScreenshotSaveResult>(
      `android/${encodeURIComponent(deviceId)}/screenshot/save`,
    ),
  tap: (deviceId: string, x: number, y: number, durationMs = 70) =>
    apiClient.post<AndroidPrimitiveResult>(
      `android/${encodeURIComponent(deviceId)}/tap`,
      {
        x,
        y,
        duration_ms: durationMs,
      },
    ),
  gesture: (deviceId: string, points: AndroidPointerPoint[]) =>
    apiClient.post<AndroidPrimitiveResult>(
      `android/${encodeURIComponent(deviceId)}/gesture`,
      { points },
    ),
  back: (deviceId: string) =>
    apiClient.post<AndroidPrimitiveResult>(
      `android/${encodeURIComponent(deviceId)}/back`,
    ),
  home: (deviceId: string) =>
    apiClient.post<AndroidPrimitiveResult>(
      `android/${encodeURIComponent(deviceId)}/home`,
    ),
  macroStart: (deviceId: string) =>
    apiClient.post<AndroidDebugState>(
      `android/${encodeURIComponent(deviceId)}/macro/start`,
    ),
  macroPause: (deviceId: string) =>
    apiClient.post<AndroidDebugState>(
      `android/${encodeURIComponent(deviceId)}/macro/pause`,
    ),
  macroStop: (deviceId: string) =>
    apiClient.post<AndroidDebugState>(
      `android/${encodeURIComponent(deviceId)}/macro/stop`,
    ),
  macroReset: (deviceId: string) =>
    apiClient.post<AndroidDebugState>(
      `android/${encodeURIComponent(deviceId)}/macro/reset`,
    ),
  macroStep: (deviceId: string) =>
    apiClient.post<AndroidDebugState>(
      `android/${encodeURIComponent(deviceId)}/macro/step`,
    ),
  streamUrl: (deviceId: string, nonce: number) =>
    apiUrl(`android/${encodeURIComponent(deviceId)}/stream?v=${nonce.toString()}`),
  screenshotUrl: (deviceId: string, nonce: string | number) =>
    apiUrl(
      `android/${encodeURIComponent(deviceId)}/screenshot?v=${encodeURIComponent(nonce.toString())}`,
    ),
  visionFrameUrl: (deviceId: string, frameId: string) =>
    apiUrl(
      `android/${encodeURIComponent(deviceId)}/vision/frame?frame_id=${encodeURIComponent(frameId)}`,
    ),
}
