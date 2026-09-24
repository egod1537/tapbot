import {
  Button,
  ButtonGroup,
  Callout,
  HTMLSelect,
  Spinner,
  Tag,
} from '@blueprintjs/core'
import { useMemo } from 'react'
import type { CameraSourceType } from '../../types/camera'
import type { CameraStreamController } from './useCameraStream'

interface CameraSourceSelectorProps {
  camera: CameraStreamController
}

const SOURCE_GROUPS: ReadonlyArray<{
  type: CameraSourceType
  label: string
}> = [
  { type: 'physical', label: 'Physical' },
  { type: 'mock_graph', label: 'Simulation' },
  { type: 'image', label: 'Image' },
  { type: 'video', label: 'Video' },
]

const ACTIVITY_LABELS = {
  switching: 'Switching…',
  refreshing: 'Refreshing…',
  reconnecting: 'Reconnecting…',
  resetting: 'Resetting…',
} as const

function displayNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null
}

function sourceTypeLabel(type: CameraSourceType | null | undefined): string {
  return SOURCE_GROUPS.find((group) => group.type === type)?.label ?? 'Unknown'
}

export function CameraSourceSelector({ camera }: CameraSourceSelectorProps) {
  const groupedSources = useMemo(
    () =>
      SOURCE_GROUPS.map((group) => ({
        ...group,
        sources: camera.sources.filter((source) => source.type === group.type),
      })).filter((group) => group.sources.length > 0),
    [camera.sources],
  )
  const selectedSource = camera.sources.find(
    (source) => source.id === camera.sourceStatus?.source_id,
  )
  const metadata = camera.sourceStatus?.metadata ?? selectedSource?.metadata
  const width = displayNumber(metadata?.width)
  const height = displayNumber(metadata?.height)
  const sourceFps = displayNumber(metadata?.fps)
  const mockGraph = camera.sourceStatus?.mock_graph
  const effectiveType = camera.sourceStatus?.type ?? selectedSource?.type
  const statusLabel = camera.sourceActivity
    ? ACTIVITY_LABELS[camera.sourceActivity]
    : camera.sourceStatus === null
      ? 'Loading…'
      : camera.sourceStatus.connected
        ? 'Connected'
        : 'Offline'
  const sourceError = camera.sourceError ?? camera.sourceStatus?.error

  return (
    <section
      className="camera-source-bar"
      aria-label="Camera source selector"
      aria-busy={camera.isSourceBusy}
    >
      <label className="focused-source-select">
        <span className="focused-control-label">Source</span>
        <HTMLSelect
          aria-label="Camera source"
          fill
          value={camera.sourceStatus?.source_id ?? ''}
          disabled={camera.isSourceBusy || camera.sources.length === 0}
          onChange={(event) => void camera.chooseSource(event.currentTarget.value)}
        >
          {camera.sources.length === 0 && <option value="">No sources</option>}
          {groupedSources.map((group) => (
            <optgroup key={group.type} label={group.label}>
              {group.sources.map((source) => (
                <option key={source.id} value={source.id} disabled={!source.available}>
                  {source.name}
                  {!source.available ? ' · Offline' : ''}
                </option>
              ))}
            </optgroup>
          ))}
        </HTMLSelect>
      </label>

      <div className="focused-source-meta" aria-live="polite">
        {camera.isSourceBusy && <Spinner size={16} />}
        <Tag
          intent={
            camera.sourceStatus === null
              ? 'warning'
              : camera.sourceStatus.connected
                ? 'success'
                : 'danger'
          }
          minimal
        >
          {statusLabel}
        </Tag>
        <Tag minimal>{sourceTypeLabel(effectiveType)}</Tag>
        <span>{width && height ? `${width} × ${height}` : '— × —'}</span>
        <span>{sourceFps ? `${sourceFps.toFixed(1)} FPS` : '— FPS'}</span>
        {mockGraph && (
          <Tag icon="diagram-tree" minimal>
            {mockGraph.current_state} · {mockGraph.available_hotspots.length} hotspots
          </Tag>
        )}
      </div>

      <ButtonGroup className="focused-source-actions">
        <Button
          icon="refresh"
          text="Refresh"
          loading={camera.sourceActivity === 'refreshing'}
          disabled={camera.isSourceBusy}
          onClick={() => void camera.refreshSources()}
        />
        <Button
          icon="repeat"
          text="Reconnect"
          loading={camera.sourceActivity === 'reconnecting'}
          disabled={camera.isSourceBusy || !camera.sourceStatus?.source_id}
          onClick={() => void camera.reconnect()}
        />
      </ButtonGroup>

      {sourceError && (
        <Callout className="focused-source-error" intent="danger" role="alert">
          {sourceError}
        </Callout>
      )}
    </section>
  )
}
