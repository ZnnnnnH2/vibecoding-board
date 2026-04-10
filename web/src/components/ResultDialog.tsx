import { useI18n } from '../i18n'

import type { HealthcheckSummary } from '../types'


type ResultDialogProps = {
  open: boolean
  providerName: string
  healthcheck: HealthcheckSummary
  onClose: () => void
}

export function ResultDialog({
  open,
  providerName,
  healthcheck,
  onClose,
}: ResultDialogProps) {
  const { messages } = useI18n()
  if (!open) {
    return null
  }

  const tone =
    healthcheck.ok === true ? 'emerald' : healthcheck.ok === false ? 'rose' : 'slate'
  const statusLabel =
    healthcheck.ok === true
      ? messages.notifications.healthcheckPassed
      : healthcheck.ok === false
        ? messages.notifications.healthcheckFailed
        : messages.healthStatus.notChecked

  return (
    <div className="confirm-backdrop" role="presentation">
      <div
        className="result-panel"
        role="dialog"
        aria-modal="true"
        aria-label={messages.notifications.healthcheckTitle(providerName)}
      >
        <span className="eyebrow">{messages.notifications.eyebrow}</span>
        <div className="result-header">
          <div className="result-copy">
            <h3>{messages.notifications.healthcheckTitle(providerName)}</h3>
            <p>{messages.notifications.healthcheckDescription}</p>
          </div>
          <span className={`pill pill-${tone}`}>{statusLabel}</span>
        </div>

        <div className="result-grid">
          <div className="result-field">
            <span className="surface-label">{messages.providers.provider}</span>
            <strong>{providerName}</strong>
          </div>
          <div className="result-field">
            <span className="surface-label">{messages.notifications.model}</span>
            <strong>{healthcheck.model ?? messages.app.noModel}</strong>
          </div>
          <div className="result-field">
            <span className="surface-label">{messages.notifications.statusCode}</span>
            <strong>{healthcheck.status_code ?? messages.app.notAvailable}</strong>
          </div>
          <div className="result-field">
            <span className="surface-label">{messages.notifications.latency}</span>
            <strong>
              {healthcheck.latency_ms == null
                ? messages.app.notAvailable
                : `${healthcheck.latency_ms} ms`}
            </strong>
          </div>
        </div>

        <div className="result-message">
          <span className="surface-label">{messages.notifications.error}</span>
          <p>{healthcheck.error ?? messages.notifications.noError}</p>
        </div>

        <div className="confirm-actions">
          <button type="button" className="accent-button" onClick={onClose}>
            {messages.notifications.close}
          </button>
        </div>
      </div>
    </div>
  )
}
