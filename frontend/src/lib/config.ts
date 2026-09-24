const DEFAULT_TIMEOUT_MS = 10_000

function normalizeBaseUrl(value: string): string {
  const trimmed = value.trim()

  if (!trimmed) {
    throw new Error('VITE_API_BASE_URL must not be empty.')
  }

  return trimmed.replace(/\/$/, '')
}

function parseTimeout(value: string | undefined): number {
  if (value === undefined) return DEFAULT_TIMEOUT_MS

  const timeout = Number(value)
  if (!Number.isFinite(timeout) || timeout <= 0) {
    console.warn(
      `Invalid VITE_API_TIMEOUT_MS value "${value}"; using ${DEFAULT_TIMEOUT_MS}ms.`,
    )
    return DEFAULT_TIMEOUT_MS
  }

  return timeout
}

export const appConfig = Object.freeze({
  apiBaseUrl: normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL),
  apiTimeoutMs: parseTimeout(import.meta.env.VITE_API_TIMEOUT_MS),
  environment: import.meta.env.MODE,
  isDevelopment: import.meta.env.DEV,
})

export function apiUrl(path: string): string {
  return `${appConfig.apiBaseUrl}/${path.replace(/^\//, '')}`
}
