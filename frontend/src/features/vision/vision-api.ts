import { apiClient } from '../../lib/api-client'
import { apiUrl } from '../../lib/config'
import type {
  PhoneScreenRunPayload,
  PhoneScreenRunResult,
  SavedVisionFrameResponse,
  ScreenPipelineRunPayload,
  ScreenPipelineRunResult,
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
  runPhoneScreen: (payload: PhoneScreenRunPayload = {}) =>
    apiClient.post<PhoneScreenRunResult>('vision/phone-screen/run', payload),
  runScreenPipeline: (payload: ScreenPipelineRunPayload) =>
    apiClient.post<ScreenPipelineRunResult>('vision/screen-pipeline/run', payload),
  rawFrameUrl: (frameId: number) => apiUrl(`vision/frames/${frameId.toString()}/raw`),
  rectifiedUrl: (resultId: number) =>
    apiUrl(`vision/results/${resultId.toString()}/rectified`),
  canonicalUrl: (resultId: number) => apiUrl(`vision/canonical/${resultId.toString()}`),
  phoneScreenOverlayUrl: (resultId: number) =>
    apiUrl(`vision/phone-screen/${resultId.toString()}/overlay`),
}
