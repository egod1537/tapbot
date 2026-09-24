import { apiClient } from '../../lib/api-client'
import type {
  MockGraphActionResponse,
  MockGraphDebugStatus,
  MockGraphTapResponse,
} from '../../types/mock-graph'

export const mockGraphApi = {
  status: (signal?: AbortSignal) =>
    apiClient.get<MockGraphDebugStatus>('mock-graph/status', { signal }),
  reset: () => apiClient.post<MockGraphActionResponse>('mock-graph/reset'),
  tap: (x: number, y: number) =>
    apiClient.post<MockGraphTapResponse>('mock-graph/tap', { x, y }),
  transition: (stateId: string) =>
    apiClient.post<MockGraphActionResponse>('mock-graph/transition', {
      state_id: stateId,
    }),
}
