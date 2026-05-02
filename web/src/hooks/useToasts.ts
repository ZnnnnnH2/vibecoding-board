import { useCallback, useEffect, useRef, useState } from 'react'

export type ToastNotification = {
  id: number
  tone: 'success' | 'error'
  text: string
}

export function useToasts() {
  const [toasts, setToasts] = useState<ToastNotification[]>([])
  const toastIdRef = useRef(0)
  const toastTimerIds = useRef(new Set<number>())

  const pushToast = useCallback((tone: ToastNotification['tone'], text: string) => {
    toastIdRef.current += 1
    setToasts((current) => [...current, { id: toastIdRef.current, tone, text }])
  }, [])

  const dismissToast = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  useEffect(() => {
    for (const toast of toasts) {
      if (toastTimerIds.current.has(toast.id)) continue
      toastTimerIds.current.add(toast.id)
      window.setTimeout(() => {
        toastTimerIds.current.delete(toast.id)
        setToasts((current) => current.filter((item) => item.id !== toast.id))
      }, 3500)
    }
  }, [toasts])

  return {
    toasts,
    pushToast,
    dismissToast,
  }
}
