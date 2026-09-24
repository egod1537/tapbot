import type { RobotToast } from '../features/robot/useRobotControl'

interface ToastProps {
  toast: RobotToast | null
  onDismiss: () => void
}

export function Toast({ toast, onDismiss }: ToastProps) {
  if (!toast) return null

  return (
    <div
      className={`toast toast--${toast.tone}`}
      role={toast.tone === 'error' ? 'alert' : 'status'}
      aria-live={toast.tone === 'error' ? 'assertive' : 'polite'}
    >
      <span className="toast__indicator" aria-hidden="true" />
      <div>
        <strong>{toast.title}</strong>
        <p>{toast.message}</p>
      </div>
      <button type="button" onClick={onDismiss} aria-label="Dismiss notification">
        ×
      </button>
    </div>
  )
}
