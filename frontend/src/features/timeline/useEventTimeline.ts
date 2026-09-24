import { useEffect, useMemo, useRef, useState } from 'react'
import type { TimelineEvent, TimelineFilter } from '../../types/timeline'
import { timelineApi } from './timeline-api'

const MAX_EVENTS = 500

const INITIAL_FILTERS: Record<TimelineFilter, boolean> = {
  camera: true,
  vision: true,
  model: true,
  robot: true,
  error: true,
}

function isTimelineEvent(value: unknown): value is TimelineEvent {
  if (typeof value !== 'object' || value === null) return false
  const event = value as Partial<TimelineEvent>
  return (
    typeof event.id === 'number' &&
    typeof event.timestamp === 'string' &&
    typeof event.message === 'string' &&
    typeof event.event_type === 'string' &&
    typeof event.category === 'string' &&
    typeof event.status === 'string'
  )
}

function matchesFilter(
  event: TimelineEvent,
  filters: Record<TimelineFilter, boolean>,
): boolean {
  if (event.status === 'error' || event.level === 'error') return filters.error
  if (event.category === 'camera') return filters.camera
  if (event.category === 'vision') return filters.vision
  if (event.category === 'model') return filters.model
  if (event.category === 'robot') return filters.robot
  return false
}

export function useEventTimeline() {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [pausedEvents, setPausedEvents] = useState<TimelineEvent[]>([])
  const [isPaused, setPaused] = useState(false)
  const [connection, setConnection] = useState<
    'connecting' | 'connected' | 'reconnecting'
  >('connecting')
  const [filters, setFilters] = useState(INITIAL_FILTERS)
  const [selectedEvent, setSelectedEvent] = useState<TimelineEvent | null>(null)
  const lastEventId = useRef(0)

  useEffect(() => {
    let active = true
    let source: EventSource | null = null

    const connect = async () => {
      try {
        const backlog = await timelineApi.entries()
        if (!active) return
        const initial = backlog.entries.slice(-MAX_EVENTS)
        setEvents(initial)
        lastEventId.current = initial.at(-1)?.id ?? 0
      } catch {
        if (active) setConnection('reconnecting')
      }
      if (!active) return

      source = new EventSource(timelineApi.streamUrl(lastEventId.current))
      source.onopen = () => {
        if (active) setConnection('connected')
      }
      source.onerror = () => {
        if (active) setConnection('reconnecting')
      }
      source.onmessage = (message) => {
        if (!active) return
        try {
          const messageData: unknown = message.data
          if (typeof messageData !== 'string') return
          const value = JSON.parse(messageData) as unknown
          if (!isTimelineEvent(value)) return
          lastEventId.current = Math.max(lastEventId.current, value.id)
          setEvents((current) => {
            if (current.some((event) => event.id === value.id)) return current
            return [...current, value].slice(-MAX_EVENTS)
          })
        } catch {
          // Ignore malformed events and keep the stream connected.
        }
      }
    }

    const initialConnection = window.setTimeout(() => void connect(), 0)
    return () => {
      active = false
      window.clearTimeout(initialConnection)
      source?.close()
    }
  }, [])

  const renderedEvents = isPaused ? pausedEvents : events
  const filteredEvents = useMemo(
    () => renderedEvents.filter((event) => matchesFilter(event, filters)),
    [filters, renderedEvents],
  )

  const togglePause = () => {
    if (isPaused) {
      setPaused(false)
      setPausedEvents([])
    } else {
      setPausedEvents(events)
      setPaused(true)
    }
  }

  const clear = () => {
    setEvents([])
    setPausedEvents([])
    setSelectedEvent(null)
  }

  const exportJson = () => {
    const blob = new Blob([JSON.stringify(filteredEvents, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `tapbot-timeline-${new Date().toISOString().replaceAll(':', '-')}.json`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  return {
    events: filteredEvents,
    totalEvents: renderedEvents.length,
    bufferedEvents: isPaused ? Math.max(0, events.length - pausedEvents.length) : 0,
    isPaused,
    connection,
    filters,
    selectedEvent,
    setSelectedEvent,
    toggleFilter: (filter: TimelineFilter) =>
      setFilters((current) => ({ ...current, [filter]: !current[filter] })),
    togglePause,
    clear,
    exportJson,
  }
}
