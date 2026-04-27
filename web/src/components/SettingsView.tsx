import { ShieldAlert } from 'lucide-react'
import { motion } from 'framer-motion'

import type { Variants } from 'framer-motion'

import { useI18n } from '../i18n'

import type {
  HealthcheckSettingsFormState,
  ResponsesWebSocketSettingsFormState,
  RetryPolicyFormState,
} from '../types'


type SettingsViewProps = {
  settingsBusy: boolean
  retryPolicyForm: RetryPolicyFormState
  retryPolicyBusy: boolean
  onRetryPolicyChange: (form: RetryPolicyFormState) => void
  onRetryPolicySubmit: (form: RetryPolicyFormState) => void
  healthcheckForm: HealthcheckSettingsFormState
  healthcheckBusy: boolean
  onHealthcheckChange: (form: HealthcheckSettingsFormState) => void
  onHealthcheckSubmit: (form: HealthcheckSettingsFormState) => void
  responsesWebSocketForm: ResponsesWebSocketSettingsFormState
  responsesWebSocketBusy: boolean
  onResponsesWebSocketChange: (form: ResponsesWebSocketSettingsFormState) => void
  onResponsesWebSocketSubmit: (form: ResponsesWebSocketSettingsFormState) => void
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
  settingsBusy,
  retryPolicyForm,
  retryPolicyBusy,
  onRetryPolicyChange,
  onRetryPolicySubmit,
  healthcheckForm,
  healthcheckBusy,
  onHealthcheckChange,
  onHealthcheckSubmit,
  responsesWebSocketForm,
  responsesWebSocketBusy,
  onResponsesWebSocketChange,
  onResponsesWebSocketSubmit,
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

  function commitRetryPolicy<K extends keyof RetryPolicyFormState>(
    key: K,
    value: RetryPolicyFormState[K],
  ) {
    const nextForm = {
      ...retryPolicyForm,
      [key]: value,
    }
    onRetryPolicyChange(nextForm)
    onRetryPolicySubmit(nextForm)
  }

  function commitHealthcheckSettings(stream: boolean) {
    const nextForm = {
      ...healthcheckForm,
      stream,
    }
    onHealthcheckChange(nextForm)
    onHealthcheckSubmit(nextForm)
  }

  function commitHealthcheckModel(model: string) {
    const nextForm = {
      ...healthcheckForm,
      model,
    }
    onHealthcheckChange(nextForm)
    onHealthcheckSubmit(nextForm)
  }

  function commitResponsesWebSocketSettings(enabled: boolean) {
    const nextForm = {
      ...responsesWebSocketForm,
      enabled,
    }
    onResponsesWebSocketChange(nextForm)
    onResponsesWebSocketSubmit(nextForm)
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
                <span className="section-caption">
                  {retryPolicyBusy ? messages.settings.savingRetryPolicy : messages.settings.blurToApply}
                </span>
              </div>

              <div className="settings-grid">
                <label className="settings-field settings-field-wide">
                  <span>{messages.settings.retryableStatusCodes}</span>
                  <textarea
                    rows={4}
                    value={retryPolicyForm.retryableStatusCodes}
                    onChange={(event) => updateRetryPolicy('retryableStatusCodes', event.target.value)}
                    onBlur={(event) =>
                      commitRetryPolicy('retryableStatusCodes', event.currentTarget.value)
                    }
                    placeholder={messages.settings.retryableStatusCodesPlaceholder}
                    disabled={settingsBusy}
                  />
                  <small className="field-hint">{messages.settings.retryableStatusCodesHint}</small>
                </label>

                <label className="settings-field settings-field-wide">
                  <span>{messages.settings.providerFailureStatusCodes}</span>
                  <textarea
                    rows={3}
                    value={retryPolicyForm.providerFailureStatusCodes}
                    onChange={(event) => updateRetryPolicy('providerFailureStatusCodes', event.target.value)}
                    onBlur={(event) =>
                      commitRetryPolicy('providerFailureStatusCodes', event.currentTarget.value)
                    }
                    placeholder={messages.settings.providerFailureStatusCodesPlaceholder}
                    disabled={settingsBusy}
                  />
                  <small className="field-hint">{messages.settings.providerFailureStatusCodesHint}</small>
                </label>

                <label className="settings-field">
                  <span>{messages.settings.sameProviderRetryCount}</span>
                  <input
                    type="number"
                    min="0"
                    step="1"
                    value={retryPolicyForm.sameProviderRetryCount}
                    onChange={(event) => updateRetryPolicy('sameProviderRetryCount', event.target.value)}
                    onBlur={(event) =>
                      commitRetryPolicy('sameProviderRetryCount', event.currentTarget.value)
                    }
                    disabled={settingsBusy}
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
                    onBlur={(event) =>
                      commitRetryPolicy('retryIntervalMs', event.currentTarget.value)
                    }
                    disabled={settingsBusy}
                  />
                  <small className="field-hint">{messages.settings.retryIntervalMsHint}</small>
                </label>
              </div>
            </section>

            <section className="settings-section">
              <div className="section-header">
                <div>
                  <span className="eyebrow">{messages.settings.responsesWebSocketEyebrow}</span>
                  <h3>{messages.settings.responsesWebSocketTitle}</h3>
                  <p>{messages.settings.responsesWebSocketCopy}</p>
                </div>
                <span className="section-caption">
                  {responsesWebSocketBusy
                    ? messages.settings.savingResponsesWebSocket
                    : messages.settings.blurToApply}
                </span>
              </div>

              <div className="form-hint-panel">
                <span className="meta-label">{messages.settings.responsesWebSocketLabel}</span>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={responsesWebSocketForm.enabled}
                    disabled={settingsBusy}
                    onChange={(event) =>
                      onResponsesWebSocketChange({
                        ...responsesWebSocketForm,
                        enabled: event.target.checked,
                      })
                    }
                    onBlur={(event) =>
                      commitResponsesWebSocketSettings(event.currentTarget.checked)
                    }
                  />
                  <span>{messages.settings.responsesWebSocketEnabled}</span>
                </label>
                <p>{messages.settings.responsesWebSocketHint}</p>
              </div>
            </section>

            <section className="settings-section">
              <div className="section-header">
                <div>
                  <span className="eyebrow">{messages.settings.healthcheckEyebrow}</span>
                  <h3>{messages.settings.healthcheckTitle}</h3>
                  <p>{messages.settings.healthcheckCopy}</p>
                </div>
                <span className="section-caption">
                  {healthcheckBusy ? messages.settings.savingHealthcheck : messages.settings.blurToApply}
                </span>
              </div>

              <div className="form-hint-panel">
                <label className="settings-field settings-field-wide">
                  <span>{messages.settings.healthcheckModel}</span>
                  <input
                    value={healthcheckForm.model}
                    onChange={(event) =>
                      onHealthcheckChange({
                        ...healthcheckForm,
                        model: event.target.value,
                      })
                    }
                    onBlur={(event) => commitHealthcheckModel(event.currentTarget.value)}
                    placeholder={messages.settings.healthcheckModelPlaceholder}
                    disabled={settingsBusy}
                  />
                  <small className="field-hint">{messages.settings.healthcheckModelHint}</small>
                </label>

                <span className="meta-label">{messages.settings.healthcheckStream}</span>
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={healthcheckForm.stream}
                    disabled={settingsBusy}
                    onChange={(event) =>
                      onHealthcheckChange({
                        ...healthcheckForm,
                        stream: event.target.checked,
                      })
                    }
                    onBlur={(event) => commitHealthcheckSettings(event.currentTarget.checked)}
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
                <li>{messages.settings.noteProviderFailureCounts}</li>
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
