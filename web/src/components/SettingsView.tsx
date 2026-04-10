import { ShieldAlert } from 'lucide-react'
import { motion } from 'framer-motion'

import { useI18n } from '../i18n'

import type { RetryPolicyFormState } from '../types'


type SettingsViewProps = {
  form: RetryPolicyFormState
  busy: boolean
  onChange: (form: RetryPolicyFormState) => void
  onSubmit: () => void
}

const containerVariants = {
  hidden: { opacity: 0, scale: 0.98 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: {
      type: 'spring',
      stiffness: 300,
      damping: 30,
      staggerChildren: 0.05,
    },
  },
}

const itemVariants = {
  hidden: { opacity: 0, y: 15 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      type: 'spring',
      stiffness: 300,
      damping: 24,
    },
  },
}

export function SettingsView({ form, busy, onChange, onSubmit }: SettingsViewProps) {
  const { messages } = useI18n()

  function update<K extends keyof RetryPolicyFormState>(key: K, value: RetryPolicyFormState[K]) {
    onChange({
      ...form,
      [key]: value,
    })
  }

  return (
    <motion.div 
      className="page-stack"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      <motion.section variants={itemVariants} className="surface-card">
        <div className="section-header">
          <div>
            <span className="eyebrow">{messages.settings.eyebrow}</span>
            <h2>{messages.settings.title}</h2>
          </div>
          <button
            type="button"
            className="accent-button"
            onClick={onSubmit}
            disabled={busy}
          >
            {busy ? messages.settings.saving : messages.settings.save}
          </button>
        </div>

        <div className="settings-layout">
          <section className="settings-section">
            <div className="settings-section-header">
              <div>
                <span className="eyebrow">{messages.settings.policyEyebrow}</span>
                <h3>{messages.settings.policyTitle}</h3>
              </div>
              <p>{messages.settings.policyCopy}</p>
            </div>

            <div className="settings-grid">
              <label className="settings-field settings-field-wide">
                <span>{messages.settings.retryableStatusCodes}</span>
                <textarea
                  rows={4}
                  value={form.retryableStatusCodes}
                  onChange={(event) => update('retryableStatusCodes', event.target.value)}
                  placeholder={messages.settings.retryableStatusCodesPlaceholder}
                />
                <small className="field-hint">{messages.settings.retryableStatusCodesHint}</small>
              </label>

              <label className="settings-field">
                <span>{messages.settings.sameProviderRetryCount}</span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={form.sameProviderRetryCount}
                  onChange={(event) => update('sameProviderRetryCount', event.target.value)}
                />
                <small className="field-hint">{messages.settings.sameProviderRetryCountHint}</small>
              </label>

              <label className="settings-field">
                <span>{messages.settings.retryIntervalMs}</span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={form.retryIntervalMs}
                  onChange={(event) => update('retryIntervalMs', event.target.value)}
                />
                <small className="field-hint">{messages.settings.retryIntervalMsHint}</small>
              </label>
            </div>
          </section>

          <section className="settings-section settings-notes">
            <div className="settings-section-header">
              <div>
                <span className="eyebrow">{messages.settings.notesEyebrow}</span>
                <h3>{messages.settings.notesTitle}</h3>
              </div>
              <ShieldAlert size={18} />
            </div>

            <ul className="note-list">
              <li>{messages.settings.noteSameProviderFirst}</li>
              <li>{messages.settings.noteFailoverAfterExhausted}</li>
              <li>{messages.settings.noteCoolingAfterExhausted}</li>
              <li>{messages.settings.noteStreamingBoundary}</li>
              <li>{messages.settings.noteClientWaits}</li>
            </ul>
          </section>
        </div>
      </motion.section>
    </motion.div>
  )
}
