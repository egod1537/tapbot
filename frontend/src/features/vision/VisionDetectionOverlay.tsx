import type { VisionDetection } from '../../types/vision'

interface VisionDetectionOverlayProps {
  width: number
  height: number
  detections: VisionDetection[]
  selectedId: string | null
  highlightedId: string | null
  onSelect: (id: string) => void
  onHighlight: (id: string | null) => void
}

export function VisionDetectionOverlay({
  width,
  height,
  detections,
  selectedId,
  highlightedId,
  onSelect,
  onHighlight,
}: VisionDetectionOverlayProps) {
  const scale = Math.max(width, height) / 900

  return (
    <svg
      className="vision-detection-overlay"
      viewBox={`0 0 ${width.toString()} ${height.toString()}`}
      preserveAspectRatio="xMidYMid meet"
      aria-label={`${detections.length.toString()} vision detections`}
    >
      {detections.map((detection) => {
        const isSelected = detection.id === selectedId
        const isHighlighted = detection.id === highlightedId
        const className = [
          'vision-overlay-detection',
          isSelected ? 'is-selected' : '',
          isHighlighted ? 'is-highlighted' : '',
        ]
          .filter(Boolean)
          .join(' ')
        return (
          <g
            className={className}
            key={detection.id}
            role="button"
            tabIndex={0}
            aria-label={`Select ${detection.label}`}
            onClick={() => onSelect(detection.id)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onSelect(detection.id)
              }
            }}
            onMouseEnter={() => onHighlight(detection.id)}
            onMouseLeave={() => onHighlight(null)}
          >
            <rect
              x={detection.bbox.x}
              y={detection.bbox.y}
              width={detection.bbox.width}
              height={detection.bbox.height}
              vectorEffect="non-scaling-stroke"
            />
            <circle
              cx={detection.center.x}
              cy={detection.center.y}
              r={Math.max(3 * scale, 2)}
              vectorEffect="non-scaling-stroke"
            />
            <text
              x={detection.bbox.x}
              y={Math.max(detection.bbox.y - 7 * scale, 12 * scale)}
            >
              {detection.label} · {(detection.confidence * 100).toFixed(1)}%
            </text>
          </g>
        )
      })}
    </svg>
  )
}
