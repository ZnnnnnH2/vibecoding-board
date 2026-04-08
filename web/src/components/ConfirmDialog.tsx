import { useI18n } from '../i18n'

type ConfirmDialogProps = {
  open: boolean
  title: string
  description: string
  busy: boolean
  onCancel: () => void
  onConfirm: () => void
}

export function ConfirmDialog({
  open,
  title,
  description,
  busy,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const { messages } = useI18n()
  if (!open) return null

  return (
    <div className="confirm-backdrop" role="presentation">
      <div 
        className="confirm-panel" 
        role="dialog" 
        aria-modal="true" 
        aria-label={title}
      >
        <span className="eyebrow">{messages.confirm.eyebrow}</span>
        <h3>{title}</h3>
        <p>{description}</p>
        <div className="confirm-actions">
          <button type="button" className="ghost-button" onClick={onCancel} disabled={busy}>
            {messages.confirm.cancel}
          </button>
          <button type="button" className="danger-button" onClick={onConfirm} disabled={busy}>
            {busy ? messages.confirm.deleteBusy : messages.confirm.deleteProvider}
          </button>
        </div>
      </div>
    </div>
  )
}
