import { ApiError } from '../../lib/api-client'
import { apiUrl, appConfig } from '../../lib/config'

export interface CameraFrameResponse {
  frameId: number
  width: number
  height: number
  capturedAt: string
  blob: Blob
}

async function parseCameraResponse(response: Response): Promise<CameraFrameResponse> {
  if (!response.ok) {
    throw new ApiError(await responseError(response), {
      code: 'CAMERA_HTTP_ERROR',
      status: response.status,
    })
  }

  const contentType = response.headers.get('Content-Type') ?? ''
  if (!contentType.startsWith('image/jpeg')) {
    throw new ApiError('Camera API returned a non-JPEG response.', {
      code: 'INVALID_CAMERA_FRAME',
      status: response.status,
    })
  }

  return {
    frameId: requiredNumberHeader(response.headers, 'X-Frame-Id'),
    width: requiredNumberHeader(response.headers, 'X-Frame-Width'),
    height: requiredNumberHeader(response.headers, 'X-Frame-Height'),
    capturedAt: response.headers.get('X-Frame-Timestamp') ?? '',
    blob: await response.blob(),
  }
}

function requiredNumberHeader(headers: Headers, name: string): number {
  const value = Number(headers.get(name))
  if (!Number.isFinite(value) || value <= 0) {
    throw new ApiError(`Camera response is missing a valid ${name} header.`, {
      code: 'INVALID_CAMERA_FRAME',
    })
  }
  return value
}

async function responseError(response: Response): Promise<string> {
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
    // Fall through to the status-based message for non-JSON responses.
  }
  return `Camera request failed (${response.status}).`
}

export async function fetchCameraFrame(
  signal: AbortSignal,
): Promise<CameraFrameResponse> {
  let response: Response
  try {
    response = await fetch(apiUrl('camera/frame'), {
      cache: 'no-store',
      headers: { Accept: 'image/jpeg' },
      signal,
    })
  } catch (error) {
    if (signal.aborted) throw error
    throw new ApiError('Unable to reach the camera API.', {
      code: 'CAMERA_NETWORK_ERROR',
      details: error,
    })
  }

  return parseCameraResponse(response)
}

export async function freezeCameraFrame(): Promise<CameraFrameResponse> {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), appConfig.apiTimeoutMs)
  let response: Response
  try {
    response = await fetch(apiUrl('camera/freeze'), {
      method: 'POST',
      cache: 'no-store',
      headers: { Accept: 'image/jpeg' },
      signal: controller.signal,
    })
  } catch (error) {
    if (controller.signal.aborted) {
      throw new ApiError('Freezing the camera frame timed out.', {
        code: 'REQUEST_TIMEOUT',
      })
    }
    throw new ApiError('Unable to freeze the camera frame.', {
      code: 'CAMERA_NETWORK_ERROR',
      details: error,
    })
  } finally {
    window.clearTimeout(timeout)
  }
  return parseCameraResponse(response)
}
