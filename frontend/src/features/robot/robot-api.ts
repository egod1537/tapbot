import { apiClient } from '../../lib/api-client'
import type {
  RobotCommandResponse,
  RobotCoordinates,
  RobotStatus,
} from '../../types/robot'

export const robotApi = {
  status: () => apiClient.get<RobotStatus>('robot/status'),
  move: (coordinates: RobotCoordinates) =>
    apiClient.post<RobotCommandResponse>('robot/move', coordinates),
  tap: (coordinates: RobotCoordinates) =>
    apiClient.post<RobotCommandResponse>('robot/tap', coordinates),
  home: () => apiClient.post<RobotCommandResponse>('robot/home'),
  penUp: () => apiClient.post<RobotCommandResponse>('robot/pen/up'),
  penDown: () => apiClient.post<RobotCommandResponse>('robot/pen/down'),
  emergencyStop: () =>
    apiClient.post<RobotCommandResponse>('robot/stop', undefined, {
      timeoutMs: 3_000,
    }),
}
