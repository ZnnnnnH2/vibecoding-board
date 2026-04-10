import { motion, AnimatePresence } from 'framer-motion'
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

  return (
    <AnimatePresence>
      {open && (
        <motion.div 
          className="confirm-backdrop" 
          role="presentation"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
        >
          <motion.div 
            className="confirm-panel" 
            role="dialog" 
            aria-modal="true" 
            aria-label={title}
            initial={{ scale: 0.95, opacity: 0, y: 10 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 10 }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
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
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
