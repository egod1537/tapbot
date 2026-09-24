import type { CameraOverlayFrame } from '../../types/camera'

export function buildDebugOverlayFixture(
  frameId: number,
  width: number,
  height: number,
): CameraOverlayFrame {
  return {
    frameId,
    frameWidth: width,
    frameHeight: height,
    items: [
      {
        id: 'phone-screen',
        kind: 'screen-corners',
        label: 'phone screen',
        color: '#b7f637',
        points: [
          { x: width * 0.22, y: height * 0.12 },
          { x: width * 0.78, y: height * 0.15 },
          { x: width * 0.75, y: height * 0.88 },
          { x: width * 0.25, y: height * 0.85 },
        ],
      },
      {
        id: 'safe-region',
        kind: 'polygon',
        label: 'safe region',
        color: '#70b8ff',
        points: [
          { x: width * 0.31, y: height * 0.27 },
          { x: width * 0.69, y: height * 0.29 },
          { x: width * 0.66, y: height * 0.74 },
          { x: width * 0.34, y: height * 0.72 },
        ],
      },
      {
        id: 'target-button',
        kind: 'bbox',
        label: 'debug target',
        confidence: 0.94,
        color: '#ffc55b',
        x: width * 0.43,
        y: height * 0.44,
        width: width * 0.17,
        height: height * 0.12,
      },
      {
        id: 'target-center',
        kind: 'center',
        label: 'center',
        confidence: 0.94,
        color: '#ff6862',
        point: { x: width * 0.515, y: height * 0.5 },
      },
    ],
  }
}
