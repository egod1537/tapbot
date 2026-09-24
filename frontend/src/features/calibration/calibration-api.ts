import { ApiError, apiClient } from '../../lib/api-client'
import { apiUrl, appConfig } from '../../lib/config'
import type { FramePoint } from '../../types/camera'
import type {
  CalibrationPayload,
  CalibrationPreview,
  CalibrationProfilesResponse,
  CalibrationResponse,
  CameraTestResult,
  ScreenTestResult,
} from '../../types/calibration'

async function previewError(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as unknown
    if (
      typeof payload === 'object' &&
      payload !== null &&
      'detail' in payload &&
      typeof payload.detail === 'string'
    ) {
      return payload.detail
    }
  } catch {
    // Use the HTTP fallback below when the response is not JSON.
  }
  return `Calibration preview failed (${response.status}).`
}

function numberHeader(headers: Headers, name: string): number {
  const value = Number(headers.get(name))
  if (!Number.isFinite(value)) {
    throw new ApiError(`Calibration preview is missing ${name}.`, {
      code: 'INVALID_CALIBRATION_PREVIEW',
    })
  }
  return value
}

async function preview(payload: CalibrationPayload): Promise<CalibrationPreview> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), appConfig.apiTimeoutMs)

  try {
    const response = await fetch(apiUrl('calibration/preview'), {
      method: 'POST',
      headers: {
        Accept: 'image/jpeg',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    })
    if (!response.ok) {
      throw new ApiError(await previewError(response), {
        code: 'CALIBRATION_PREVIEW_ERROR',
        status: response.status,
      })
    }
    return {
      blob: await response.blob(),
      width: numberHeader(response.headers, 'X-Preview-Width'),
      height: numberHeader(response.headers, 'X-Preview-Height'),
      centerRobot: {
        x: numberHeader(response.headers, 'X-Center-Robot-X'),
        y: numberHeader(response.headers, 'X-Center-Robot-Y'),
      },
    }
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (controller.signal.aborted) {
      throw new ApiError('Calibration preview timed out.', {
        code: 'REQUEST_TIMEOUT',
      })
    }
    throw new ApiError('Unable to reach the calibration API.', {
      code: 'NETWORK_ERROR',
      details: error,
    })
  } finally {
    window.clearTimeout(timeout)
  }
}

export const calibrationApi = {
  profiles: () => apiClient.get<CalibrationProfilesResponse>('calibration/profiles'),
  get: (profile?: string) =>
    apiClient.get<CalibrationResponse>(
      profile ? `calibration?profile=${encodeURIComponent(profile)}` : 'calibration',
    ),
  save: (payload: CalibrationPayload) =>
    apiClient.post<CalibrationResponse>('calibration', payload),
  activate: (profile: string) =>
    apiClient.post<CalibrationResponse>(
      `calibration/activate?profile=${encodeURIComponent(profile)}`,
    ),
  preview,
  cameraToRobot: (point: FramePoint) =>
    apiClient.post<CameraTestResult>('calibration/camera-to-robot', point),
  screenToRobot: (point: FramePoint) =>
    apiClient.post<ScreenTestResult>('calibration/screen-to-robot', point),
}
