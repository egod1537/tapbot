import { apiClient } from '../../lib/api-client'
import { apiUrl } from '../../lib/config'
import type {
  AndroidDebugState,
  AndroidPrimitiveResult,
  AndroidProxyStatus,
  AndroidScreenshotSaveResult,
} from '../../types/android-debug'

export const androidApi = {
  status: (signal?: AbortSignal) =>
    apiClient.get<AndroidProxyStatus>('android/status', { signal }),
  debugState: (signal?: AbortSignal) =>
    apiClient.get<AndroidDebugState>('android/debug/state', { signal }),
  runVision: () => apiClient.post<AndroidDebugState>('android/vision/run'),
  saveScreenshot: () =>
    apiClient.post<AndroidScreenshotSaveResult>('android/screenshot/save'),
  tap: (x: number, y: number, durationMs = 70) =>
    apiClient.post<AndroidPrimitiveResult>('android/tap', {
      x,
      y,
      duration_ms: durationMs,
    }),
  back: () => apiClient.post<AndroidPrimitiveResult>('android/back'),
  home: () => apiClient.post<AndroidPrimitiveResult>('android/home'),
  macroStart: () => apiClient.post<AndroidDebugState>('android/macro/start'),
  macroPause: () => apiClient.post<AndroidDebugState>('android/macro/pause'),
  macroStop: () => apiClient.post<AndroidDebugState>('android/macro/stop'),
  macroReset: () => apiClient.post<AndroidDebugState>('android/macro/reset'),
  macroStep: () => apiClient.post<AndroidDebugState>('android/macro/step'),
  streamUrl: (nonce: number) => apiUrl(`android/stream?v=${nonce.toString()}`),
  screenshotUrl: (nonce: string | number) =>
    apiUrl(`android/screenshot?v=${encodeURIComponent(nonce.toString())}`),
  visionFrameUrl: (frameId: string) =>
    apiUrl(`android/vision/frame?frame_id=${encodeURIComponent(frameId)}`),
}
