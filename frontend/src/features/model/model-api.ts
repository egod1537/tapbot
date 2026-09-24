import { apiClient } from '../../lib/api-client'
import { apiUrl } from '../../lib/config'
import type { ModelRunPayload, ModelRunResult, ModelStatus } from '../../types/model'

export const modelApi = {
  status: () => apiClient.get<ModelStatus>('model/status'),
  run: (payload: ModelRunPayload) =>
    apiClient.post<ModelRunResult>('model/run', payload),
  inputImageUrl: (runId: number) => apiUrl(`model/runs/${runId.toString()}/input`),
}
