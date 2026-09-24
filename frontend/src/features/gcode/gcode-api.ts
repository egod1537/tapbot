import { apiClient } from '../../lib/api-client'
import type { GcodeCapabilities, GcodeCommandResponse } from '../../types/gcode'

export const gcodeApi = {
  capabilities: () => apiClient.get<GcodeCapabilities>('gcode/capabilities'),
  send: (command: string) =>
    apiClient.post<GcodeCommandResponse>('gcode/command', { command }),
}
