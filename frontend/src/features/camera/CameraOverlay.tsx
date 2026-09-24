import type {
  CameraOverlayFrame,
  CameraOverlayItem,
  FramePoint,
} from '../../types/camera'

interface CameraOverlayProps {
  overlay: CameraOverlayFrame
  showLabels: boolean
  showConfidence: boolean
}

function pointList(points: FramePoint[]): string {
  return points.map(({ x, y }) => `${x},${y}`).join(' ')
}

function labelAnchor(item: CameraOverlayItem): FramePoint {
  switch (item.kind) {
    case 'bbox':
      return { x: item.x, y: item.y }
    case 'center':
      return item.point
    case 'polygon':
    case 'screen-corners':
      return item.points[0] ?? { x: 0, y: 0 }
  }
}

function overlayText(
  item: CameraOverlayItem,
  showLabels: boolean,
  showConfidence: boolean,
): string {
  const values: string[] = []
  if (showLabels && item.label) values.push(item.label)
  if (showConfidence && item.confidence !== undefined) {
    values.push(`${Math.round(item.confidence * 100)}%`)
  }
  return values.join(' · ')
}

export function CameraOverlay({
  overlay,
  showLabels,
  showConfidence,
}: CameraOverlayProps) {
  const unit = Math.max(overlay.frameWidth, overlay.frameHeight) / 1_000
  const strokeWidth = Math.max(unit * 2, 1)
  const pointRadius = Math.max(unit * 4, 2)
  const fontSize = Math.max(unit * 15, 8)

  return (
    <svg
      className="camera-overlay"
      viewBox={`0 0 ${overlay.frameWidth} ${overlay.frameHeight}`}
      preserveAspectRatio="xMidYMid meet"
      aria-label={`Debug overlay with ${overlay.items.length} items`}
    >
      {overlay.items.map((item) => {
        const color = item.color ?? '#b7f637'
        const text = overlayText(item, showLabels, showConfidence)
        const anchor = labelAnchor(item)

        return (
          <g className={`overlay-item overlay-item--${item.kind}`} key={item.id}>
            {item.kind === 'screen-corners' && (
              <>
                <polygon
                  points={pointList(item.points)}
                  fill={color}
                  fillOpacity={0.07}
                  stroke={color}
                  strokeWidth={strokeWidth}
                  vectorEffect="non-scaling-stroke"
                />
                {item.points.map((point, index) => (
                  <circle
                    key={`${item.id}-${index.toString()}`}
                    cx={point.x}
                    cy={point.y}
                    r={pointRadius}
                    fill="#0a0e0c"
                    stroke={color}
                    strokeWidth={strokeWidth}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
              </>
            )}
            {item.kind === 'polygon' && (
              <polygon
                points={pointList(item.points)}
                fill={color}
                fillOpacity={0.05}
                stroke={color}
                strokeDasharray={`${strokeWidth * 4} ${strokeWidth * 3}`}
                strokeWidth={strokeWidth}
                vectorEffect="non-scaling-stroke"
              />
            )}
            {item.kind === 'bbox' && (
              <rect
                x={item.x}
                y={item.y}
                width={item.width}
                height={item.height}
                fill={color}
                fillOpacity={0.05}
                stroke={color}
                strokeWidth={strokeWidth}
                vectorEffect="non-scaling-stroke"
              />
            )}
            {item.kind === 'center' && (
              <>
                <circle
                  cx={item.point.x}
                  cy={item.point.y}
                  r={pointRadius * 1.7}
                  fill="none"
                  stroke={color}
                  strokeWidth={strokeWidth}
                  vectorEffect="non-scaling-stroke"
                />
                <line
                  x1={item.point.x - pointRadius * 2.7}
                  x2={item.point.x + pointRadius * 2.7}
                  y1={item.point.y}
                  y2={item.point.y}
                  stroke={color}
                  strokeWidth={strokeWidth}
                  vectorEffect="non-scaling-stroke"
                />
                <line
                  x1={item.point.x}
                  x2={item.point.x}
                  y1={item.point.y - pointRadius * 2.7}
                  y2={item.point.y + pointRadius * 2.7}
                  stroke={color}
                  strokeWidth={strokeWidth}
                  vectorEffect="non-scaling-stroke"
                />
              </>
            )}
            {text && (
              <text
                x={anchor.x}
                y={Math.max(anchor.y - fontSize * 0.45, fontSize)}
                fill={color}
                stroke="#080b09"
                strokeWidth={strokeWidth * 2}
                paintOrder="stroke"
                fontFamily="var(--mono)"
                fontSize={fontSize}
                fontWeight="600"
              >
                {text}
              </text>
            )}
          </g>
        )
      })}
    </svg>
  )
}
