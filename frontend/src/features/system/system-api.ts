import { apiClient } from '../../lib/api-client'
import type { BackendSystemStatus } from '../../types/system'

export const systemApi = {
  status: () => apiClient.get<BackendSystemStatus>('status'),
}
