import { apiUrl, appConfig } from './config'
import type { ApiErrorResponse } from '../types/api'

export type ApiErrorCode =
  | 'HTTP_ERROR'
  | 'INVALID_JSON'
  | 'NETWORK_ERROR'
  | 'REQUEST_ABORTED'
  | 'REQUEST_TIMEOUT'

export class ApiError extends Error {
  readonly code: string
  readonly status?: number
  readonly details?: unknown

  constructor(
    message: string,
    options: { code: string; status?: number; details?: unknown },
  ) {
    super(message)
    this.name = 'ApiError'
    this.code = options.code
    this.status = options.status
    this.details = options.details
  }
}

export interface ApiRequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  timeoutMs?: number
}

function parseJson(text: string, status: number): unknown {
  if (text.length === 0) return undefined

  try {
    return JSON.parse(text) as unknown
  } catch (error) {
    throw new ApiError('The server returned an invalid JSON response.', {
      code: 'INVALID_JSON',
      status,
      details: error,
    })
  }
}

function isErrorResponse(value: unknown): value is ApiErrorResponse {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Partial<ApiErrorResponse>
  return (
    candidate.ok === false &&
    typeof candidate.error === 'object' &&
    candidate.error !== null &&
    typeof candidate.error.message === 'string' &&
    typeof candidate.error.code === 'string'
  )
}

function fastApiErrorMessage(value: unknown): string | undefined {
  if (typeof value !== 'object' || value === null || !('detail' in value)) {
    return undefined
  }

  const { detail } = value
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return undefined

  const messages = (detail as unknown[]).flatMap((item) => {
    if (typeof item !== 'object' || item === null || !('msg' in item)) return []
    const { msg } = item
    return typeof msg === 'string' ? [msg] : []
  })
  return messages.length > 0 ? messages.join('; ') : undefined
}

async function request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const controller = new AbortController()
  const timeoutMs = options.timeoutMs ?? appConfig.apiTimeoutMs
  let timedOut = false

  const timeoutId = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  const abortFromCaller = () => controller.abort(options.signal?.reason)
  options.signal?.addEventListener('abort', abortFromCaller, { once: true })

  const headers = new Headers(options.headers)
  headers.set('Accept', 'application/json')

  const hasBody = options.body !== undefined
  if (hasBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  try {
    const response = await fetch(apiUrl(path), {
      ...options,
      body: hasBody ? JSON.stringify(options.body) : undefined,
      headers,
      signal: controller.signal,
    })
    const payload = parseJson(await response.text(), response.status)

    if (!response.ok) {
      const apiError = isErrorResponse(payload) ? payload.error : undefined
      throw new ApiError(
        apiError?.message ??
          fastApiErrorMessage(payload) ??
          `Request failed (${response.status}).`,
        {
          code: apiError?.code ?? 'HTTP_ERROR',
          status: response.status,
          details: apiError?.details ?? payload,
        },
      )
    }

    return payload as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    if (timedOut) {
      throw new ApiError(`Request timed out after ${timeoutMs}ms.`, {
        code: 'REQUEST_TIMEOUT',
      })
    }
    if (controller.signal.aborted) {
      throw new ApiError('Request was aborted.', { code: 'REQUEST_ABORTED' })
    }
    throw new ApiError('Unable to reach the API server.', {
      code: 'NETWORK_ERROR',
      details: error,
    })
  } finally {
    window.clearTimeout(timeoutId)
    options.signal?.removeEventListener('abort', abortFromCaller)
  }
}

export const apiClient = {
  get: <T>(path: string, options?: ApiRequestOptions) =>
    request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, options?: ApiRequestOptions) =>
    request<T>(path, { ...options, method: 'PUT', body }),
  delete: <T>(path: string, options?: ApiRequestOptions) =>
    request<T>(path, { ...options, method: 'DELETE' }),
}
