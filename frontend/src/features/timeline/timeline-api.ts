import { apiClient } from '../../lib/api-client'
import { apiUrl } from '../../lib/config'
import type { TimelineEventsResponse } from '../../types/timeline'

export const timelineApi = {
  entries: (afterId = 0) =>
    apiClient.get<TimelineEventsResponse>(`logs?after_id=${afterId.toString()}`),
  streamUrl: (afterId: number) =>
    apiUrl(`events/stream?after_id=${afterId.toString()}`),
}
