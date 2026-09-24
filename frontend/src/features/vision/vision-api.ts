import { apiClient } from '../../lib/api-client'
import { apiUrl } from '../../lib/config'
import type {
  SavedVisionFrameResponse,
  VisionCapabilities,
  VisionFramesResponse,
  VisionRunPayload,
  VisionRunResult,
} from '../../types/vision'

export const visionApi = {
  capabilities: () => apiClient.get<VisionCapabilities>('vision/capabilities'),
  frames: () => apiClient.get<VisionFramesResponse>('vision/frames'),
  saveFrame: () => apiClient.post<SavedVisionFrameResponse>('vision/frames'),
  run: (payload: VisionRunPayload) =>
    apiClient.post<VisionRunResult>('vision/run', payload),
  rawFrameUrl: (frameId: number) => apiUrl(`vision/frames/${frameId.toString()}/raw`),
  rectifiedUrl: (resultId: number) =>
    apiUrl(`vision/results/${resultId.toString()}/rectified`),
}
