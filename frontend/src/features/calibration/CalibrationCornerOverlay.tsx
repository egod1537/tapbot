import type { FramePoint } from '../../types/camera'

const CORNER_NAMES = ['TL', 'TR', 'BR', 'BL'] as const

interface CalibrationCornerOverlayProps {
  width: number
  height: number
  points: FramePoint[]
  testPoint?: FramePoint | null
}

export function CalibrationCornerOverlay({
  width,
  height,
  points,
  testPoint,
}: CalibrationCornerOverlayProps) {
  const scale = Math.max(width, height) / 1_000
  const radius = Math.max(scale * 7, 3)
  const fontSize = Math.max(scale * 17, 9)

  return (
    <svg
      className="calibration-corner-overlay"
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {points.length > 1 && (
        <polyline
          points={points.map(({ x, y }) => `${x},${y}`).join(' ')}
          fill="none"
          stroke="#b7f637"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      )}
      {points.length === 4 && (
        <line
          x1={points[3]?.x}
          y1={points[3]?.y}
          x2={points[0]?.x}
          y2={points[0]?.y}
          stroke="#b7f637"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      )}
      {points.map((point, index) => (
        <g key={CORNER_NAMES[index]}>
          <circle
            cx={point.x}
            cy={point.y}
            r={radius}
            fill="#0a0e0c"
            stroke="#b7f637"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
          <text
            x={point.x + radius * 1.4}
            y={point.y - radius * 1.2}
            fill="#b7f637"
            stroke="#080b09"
            strokeWidth={scale * 3}
            paintOrder="stroke"
            fontFamily="var(--mono)"
            fontSize={fontSize}
            fontWeight="700"
          >
            {CORNER_NAMES[index]}
          </text>
        </g>
      ))}
      {testPoint && (
        <g>
          <circle
            cx={testPoint.x}
            cy={testPoint.y}
            r={radius * 1.5}
            fill="none"
            stroke="#ff6862"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1={testPoint.x - radius * 2.3}
            x2={testPoint.x + radius * 2.3}
            y1={testPoint.y}
            y2={testPoint.y}
            stroke="#ff6862"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
          <line
            x1={testPoint.x}
            x2={testPoint.x}
            y1={testPoint.y - radius * 2.3}
            y2={testPoint.y + radius * 2.3}
            stroke="#ff6862"
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
        </g>
      )}
    </svg>
  )
}
