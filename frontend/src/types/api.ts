export interface ApiErrorBody {
  code: string
  message: string
  details?: unknown
}

export interface ApiSuccessResponse<T> {
  ok: true
  data: T
  requestId?: string
}

export interface ApiErrorResponse {
  ok: false
  error: ApiErrorBody
  requestId?: string
}

export type ApiResponse<T> = ApiSuccessResponse<T> | ApiErrorResponse

export interface HealthStatus {
  status: 'ok' | 'degraded' | 'offline'
  version: string
  timestamp: string
}
