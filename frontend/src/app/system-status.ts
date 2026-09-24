import { createContext, useContext } from 'react'
import type { SystemStatusContextValue } from '../types/system'

export const SystemStatusContext = createContext<SystemStatusContextValue | null>(null)

export function useSystemStatus(): SystemStatusContextValue {
  const context = useContext(SystemStatusContext)
  if (!context) {
    throw new Error('useSystemStatus must be used inside SystemStatusProvider.')
  }
  return context
}
