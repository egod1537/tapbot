export type TimelineCategory =
  'android' | 'camera' | 'macro' | 'vision' | 'model' | 'robot' | 'system'

export interface TimelineEvent {
  id: number
  timestamp: string
  level: string
  message: string
  event_type: string
  category: TimelineCategory
  status: string
  trace_id: string | null
  latency_ms: number | null
  payload: Record<string, unknown>
}

export interface TimelineEventsResponse {
  entries: TimelineEvent[]
}

export type TimelineFilter = 'camera' | 'vision' | 'model' | 'robot' | 'error'
