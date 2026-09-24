import { Panel } from '../../components/Panel'
import type { TimelineCategory, TimelineFilter } from '../../types/timeline'
import { JsonSyntaxHighlight } from '../model/JsonSyntaxHighlight'
import { useEventTimeline } from '../timeline/useEventTimeline'

const FILTERS: { id: TimelineFilter; label: string }[] = [
  { id: 'camera', label: 'Camera' },
  { id: 'vision', label: 'Vision' },
  { id: 'model', label: 'Model' },
  { id: 'robot', label: 'Robot' },
  { id: 'error', label: 'Error' },
]

function timestamp(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleTimeString(undefined, {
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    fractionalSecondDigits: 3,
  })
}

function categoryLabel(category: TimelineCategory): string {
  return category === 'system'
    ? 'System'
    : category.charAt(0).toUpperCase() + category.slice(1)
}

export function TimelinePanel() {
  const timeline = useEventTimeline()

  return (
    <Panel
      title="Timeline / Event Stream"
      eyebrow="Live correlated session trace"
      className="timeline-panel"
      actions={
        <>
          <span className={`timeline-connection is-${timeline.connection}`}>
            {timeline.connection}
          </span>
          <span className="log-count">{timeline.totalEvents} events</span>
          <button type="button" className="text-button" onClick={timeline.togglePause}>
            {timeline.isPaused ? 'Resume' : 'Pause'}
          </button>
          <button type="button" className="text-button" onClick={timeline.exportJson}>
            Export
          </button>
          <button type="button" className="text-button" onClick={timeline.clear}>
            Clear
          </button>
        </>
      }
    >
      <div className="timeline-toolbar">
        <div className="timeline-filters" aria-label="Timeline filters">
          {FILTERS.map((filter) => (
            <button
              type="button"
              className={
                timeline.filters[filter.id] ? `is-active is-${filter.id}` : undefined
              }
              aria-pressed={timeline.filters[filter.id]}
              key={filter.id}
              onClick={() => timeline.toggleFilter(filter.id)}
            >
              <i aria-hidden="true" />
              {filter.label}
            </button>
          ))}
        </div>
        <div
          className={
            timeline.isPaused ? 'timeline-pause-note is-paused' : 'timeline-pause-note'
          }
        >
          <span>{timeline.isPaused ? 'Rendering paused' : 'Live rendering'}</span>
          {timeline.isPaused && (
            <strong>+{timeline.bufferedEvents.toString()} events buffered</strong>
          )}
        </div>
      </div>

      <div
        className={
          timeline.selectedEvent ? 'timeline-layout has-detail' : 'timeline-layout'
        }
      >
        <div
          className="event-table"
          role="table"
          aria-label="Live TapBot event timeline"
        >
          <div className="event-table__header" role="row">
            <span role="columnheader">Time</span>
            <span role="columnheader">Category</span>
            <span role="columnheader">Event / message</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">Latency</span>
            <span role="columnheader">Trace</span>
          </div>
          <div className="event-table__body">
            {timeline.events.length === 0 ? (
              <div className="timeline-empty">Waiting for matching events…</div>
            ) : (
              timeline.events.map((event, index) => {
                const continuesTrace =
                  index > 0 && timeline.events[index - 1]?.trace_id === event.trace_id
                return (
                  <button
                    type="button"
                    role="row"
                    className={[
                      `event-row is-${event.status}`,
                      continuesTrace && event.trace_id ? 'is-trace-continuation' : '',
                      timeline.selectedEvent?.id === event.id ? 'is-selected' : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    key={event.id}
                    onClick={() => timeline.setSelectedEvent(event)}
                  >
                    <time role="cell">{timestamp(event.timestamp)}</time>
                    <span role="cell" className={`event-category is-${event.category}`}>
                      {categoryLabel(event.category)}
                    </span>
                    <span role="cell" className="event-message">
                      <code>{event.event_type}</code>
                      <span>{event.message}</span>
                    </span>
                    <span role="cell" className="event-status">
                      <i aria-hidden="true" />
                      {event.status}
                    </span>
                    <span role="cell" className="event-latency">
                      {event.latency_ms === null
                        ? '—'
                        : `${event.latency_ms.toFixed(1)} ms`}
                    </span>
                    <code
                      role="cell"
                      className="event-trace"
                      title={event.trace_id ?? ''}
                    >
                      {event.trace_id ?? 'unscoped'}
                    </code>
                  </button>
                )
              })
            )}
          </div>
        </div>

        {timeline.selectedEvent && (
          <aside className="event-detail-drawer">
            <header>
              <div>
                <span>Event detail</span>
                <strong>{timeline.selectedEvent.event_type}</strong>
              </div>
              <button type="button" onClick={() => timeline.setSelectedEvent(null)}>
                ×
              </button>
            </header>
            <dl>
              <div>
                <dt>Timestamp</dt>
                <dd>{timeline.selectedEvent.timestamp}</dd>
              </div>
              <div>
                <dt>Trace ID</dt>
                <dd>{timeline.selectedEvent.trace_id ?? 'unscoped'}</dd>
              </div>
              <div>
                <dt>Category</dt>
                <dd>{timeline.selectedEvent.category}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{timeline.selectedEvent.status}</dd>
              </div>
              <div>
                <dt>Latency</dt>
                <dd>
                  {timeline.selectedEvent.latency_ms === null
                    ? 'Not measured'
                    : `${timeline.selectedEvent.latency_ms.toFixed(3)} ms`}
                </dd>
              </div>
              <div>
                <dt>Message</dt>
                <dd>{timeline.selectedEvent.message}</dd>
              </div>
            </dl>
            <div className="event-detail-payload">
              <span>Payload</span>
              <JsonSyntaxHighlight value={timeline.selectedEvent.payload} />
            </div>
          </aside>
        )}
      </div>
    </Panel>
  )
}
