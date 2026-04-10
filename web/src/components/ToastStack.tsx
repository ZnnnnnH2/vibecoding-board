import { X } from 'lucide-react'

import { useI18n } from '../i18n'


type Toast = {
  id: number
  tone: 'success' | 'error'
  text: string
}

type ToastStackProps = {
  toasts: Toast[]
  onDismiss: (id: number) => void
}

export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  const { messages } = useI18n()
  if (toasts.length === 0) {
    return null
  }

  return (
    <div className="toast-stack" aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast-card toast-card-${toast.tone}`} role="status">
          <p>{toast.text}</p>
          <button
            type="button"
            className="toast-dismiss"
            onClick={() => onDismiss(toast.id)}
            aria-label={messages.notifications.dismissToast}
          >
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  )
}
