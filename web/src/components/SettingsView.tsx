import { Save, ShieldAlert } from 'lucide-react'
import { motion } from 'framer-motion'

import type { Variants } from 'framer-motion'

import { useI18n } from '../i18n'

import type { HealthcheckSettingsFormState, RetryPolicyFormState } from '../types'


type SettingsViewProps = {
  retryPolicyForm: RetryPolicyFormState
  retryPolicyBusy: boolean
  onRetryPolicyChange: (form: RetryPolicyFormState) => void
  onRetryPolicySubmit: () => void
  healthcheckForm: HealthcheckSettingsFormState
  healthcheckBusy: boolean
  onHealthcheckChange: (form: HealthcheckSettingsFormState) => void
  onHealthcheckSubmit: () => void
}

const containerVariants: Variants = {
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

const itemVariants: Variants = {
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

export function SettingsView({
  retryPolicyForm,
  retryPolicyBusy,
  onRetryPolicyChange,
  onRetryPolicySubmit,
  healthcheckForm,
  healthcheckBusy,
  onHealthcheckChange,
  onHealthcheckSubmit,
}: SettingsViewProps) {
  const { messages } = useI18n()

  function updateRetryPolicy<K extends keyof RetryPolicyFormState>(
    key: K,
    value: RetryPolicyFormState[K],
  ) {
    onRetryPolicyChange({
      ...retryPolicyForm,
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
          <span className="section-caption">{messages.settings.title}</span>
        </div>

        <div className="settings-layout">
          <div className="list-stack">
            <section className="settings-section">
              <div className="section-header">
                <div>
                  <span className="eyebrow">{messages.settings.policyEyebrow}</span>
                  <h3>{messages.settings.policyTitle}</h3>
                  <p>{messages.settings.policyCopy}</p>
                </div>
                <button
                  type="button"
                  className="accent-button"
                  onClick={onRetryPolicySubmit}
                  disabled={retryPolicyBusy}
                >
                  <Save size={16} />
                  {retryPolicyBusy
                    ? messages.settings.savingRetryPolicy
                    : messages.settings.saveRetryPolicy}
                </button>
              </div>

              <div className="settings-grid">
                <label className="settings-field settings-field-wide">
                  <span>{messages.settings.retryableStatusCodes}</span>
                  <textarea
                    rows={4}
                    value={retryPolicyForm.retryableStatusCodes}
                    onChange={(event) => updateRetryPolicy('retryableStatusCodes', event.target.value)}
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
                    value={retryPolicyForm.sameProviderRetryCount}
                    onChange={(event) => updateRetryPolicy('sameProviderRetryCount', event.target.value)}
                  />
                  <small className="field-hint">{messages.settings.sameProviderRetryCountHint}</small>
                </label>

                <label className="settings-field">
                  <span>{messages.settings.retryIntervalMs}</span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={retryPolicyForm.retryIntervalMs}
                    onChange={(event) => updateRetryPolicy('retryIntervalMs', event.target.value)}
                  />
                  <small className="field-hint">{messages.settings.retryIntervalMsHint}</small>
                </label>
              </div>
            </section>

            <section className="settings-section">
              <div className="section-header">
                <div>
                  <span className="eyebrow">{messages.settings.healthcheckEyebrow}</span>
                  <h3>{messages.settings.healthcheckTitle}</h3>
                  <p>{messages.settings.healthcheckCopy}</p>
                </div>
                <button
                  type="button"
                  className="accent-button"
                  onClick={onHealthcheckSubmit}
                  disabled={healthcheckBusy}
                >
                  <Save size={16} />
                  {healthcheckBusy
                    ? messages.settings.savingHealthcheck
                    : messages.settings.saveHealthcheck}
                </button>
              </div>

              <div className="form-hint-panel">
                <span className="meta-label">{messages.settings.healthcheckStream}</span>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={healthcheckForm.stream}
                    onChange={(event) =>
                      onHealthcheckChange({
                        ...healthcheckForm,
                        stream: event.target.checked,
                      })
                    }
                  />
                  <span>{messages.settings.healthcheckStreamEnabled}</span>
                </label>
                <p>{messages.settings.healthcheckStreamHint}</p>
              </div>
            </section>
          </div>

          <aside className="list-stack">
            <section className="settings-section settings-notes">
              <div className="settings-section-header">
                <div>
                  <span className="eyebrow">{messages.settings.notesEyebrow}</span>
                  <h3>{messages.settings.notesTitle}</h3>
                </div>
                <ShieldAlert size={18} className="chart-card-icon-neutral" />
              </div>

              <ul className="note-list">
                <li>{messages.settings.noteSameProviderFirst}</li>
                <li>{messages.settings.noteFailoverAfterExhausted}</li>
                <li>{messages.settings.noteCoolingAfterExhausted}</li>
                <li>{messages.settings.noteStreamingBoundary}</li>
                <li>{messages.settings.noteClientWaits}</li>
              </ul>
            </section>
          </aside>
        </div>
      </motion.section>
    </motion.div>
  )
}
