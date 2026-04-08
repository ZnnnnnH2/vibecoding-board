import type { FormEvent } from 'react'

import { useI18n } from '../i18n'
import type { ProviderFormState } from '../types'

type ProviderDrawerProps = {
  open: boolean
  mode: 'create' | 'edit'
  busy: boolean
  form: ProviderFormState
  onClose: () => void
  onChange: (next: ProviderFormState) => void
  onSubmit: () => void
}

export function ProviderDrawer({
  open,
  mode,
  busy,
  form,
  onClose,
  onChange,
  onSubmit,
}: ProviderDrawerProps) {
  const { messages } = useI18n()
  const submitLabel = mode === 'create' ? messages.drawer.addProvider : messages.drawer.saveChanges

  function update<K extends keyof ProviderFormState>(key: K, value: ProviderFormState[K]) {
    onChange({
      ...form,
      [key]: value,
    })
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    onSubmit()
  }

  if (!open) return null

  return (
    <div className="drawer-backdrop" role="presentation">
      <aside className="drawer-panel">
        <div className="drawer-header">
          <div>
            <span className="eyebrow">{mode === 'create' ? messages.drawer.newUpstream : messages.drawer.editUpstream}</span>
            <h2>{mode === 'create' ? messages.drawer.addProvider : messages.drawer.refineProviderDetails}</h2>
          </div>
          <button type="button" className="ghost-button" onClick={onClose} disabled={busy}>
            {messages.drawer.close}
          </button>
        </div>

        <form className="drawer-form" onSubmit={handleSubmit}>
          <section className="drawer-section">
            <div className="drawer-section-header">
              <div>
                <span className="eyebrow">{messages.drawer.identityEyebrow}</span>
                <h3>{messages.drawer.connectionDetails}</h3>
              </div>
              <p className="drawer-section-copy">{messages.drawer.identityCopy}</p>
            </div>

            <div className="drawer-field-grid">
              <label>
                <span>{messages.drawer.name}</span>
                <input
                  value={form.name}
                  onChange={(event) => update('name', event.target.value)}
                  placeholder={messages.drawer.namePlaceholder}
                  required
                />
                <small className="field-hint">{messages.drawer.nameHint}</small>
              </label>

              <label>
                <span>{messages.drawer.baseUrl}</span>
                <input
                  value={form.baseUrl}
                  onChange={(event) => update('baseUrl', event.target.value)}
                  placeholder={messages.drawer.baseUrlPlaceholder}
                  required
                />
                <small className="field-hint">{messages.drawer.baseUrlHint}</small>
              </label>

              <label className="drawer-field-span">
                <span>{messages.drawer.apiKey}</span>
                <input
                  value={form.apiKey}
                  onChange={(event) => update('apiKey', event.target.value)}
                  placeholder={mode === 'edit' ? messages.drawer.apiKeyEditPlaceholder : messages.drawer.apiKeyCreatePlaceholder}
                  required={mode === 'create'}
                />
                <small className="field-hint">{messages.drawer.apiKeyHint}</small>
              </label>
            </div>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => update('enabled', event.target.checked)}
              />
              <span>{messages.drawer.enableAfterSave}</span>
            </label>
          </section>

          <section className="drawer-section">
            <div className="drawer-section-header">
              <div>
                <span className="eyebrow">{messages.drawer.routingEyebrow}</span>
                <h3>{messages.drawer.selectionRules}</h3>
              </div>
              <p className="drawer-section-copy">{messages.drawer.routingCopy}</p>
            </div>

            <div className="drawer-field-grid">
              <label>
                <span>{messages.drawer.priority}</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={form.priority}
                  onChange={(event) => update('priority', event.target.value)}
                  required
                />
                <small className="field-hint">{messages.drawer.priorityHint}</small>
              </label>

              <label>
                <span>{messages.drawer.healthcheckModel}</span>
                <input
                  value={form.healthcheckModel}
                  onChange={(event) => update('healthcheckModel', event.target.value)}
                  placeholder={form.modelMode === 'all' ? messages.drawer.wildcardPlaceholder : messages.drawer.healthcheckPlaceholder}
                />
                <small className="field-hint">{messages.drawer.healthcheckHint}</small>
              </label>
            </div>

            <div className="segment-control">
              <button
                type="button"
                className={form.modelMode === 'all' ? 'segment-active' : ''}
                onClick={() => update('modelMode', 'all')}
              >
                {messages.drawer.allModels}
              </button>
              <button
                type="button"
                className={form.modelMode === 'explicit' ? 'segment-active' : ''}
                onClick={() => update('modelMode', 'explicit')}
              >
                {messages.drawer.explicitList}
              </button>
            </div>

            {form.modelMode === 'explicit' ? (
              <label>
                <span>{messages.drawer.models}</span>
                <textarea
                  rows={6}
                  value={form.modelText}
                  onChange={(event) => update('modelText', event.target.value)}
                  placeholder={messages.drawer.modelsPlaceholder}
                  required
                />
                <small className="field-hint">{messages.drawer.modelsHint}</small>
              </label>
            ) : (
              <div className="form-hint-panel">
                <span className="meta-label">{messages.drawer.wildcardRouting}</span>
                <p>{messages.drawer.wildcardRoutingCopy}</p>
              </div>
            )}
          </section>

          <section className="drawer-section">
            <div className="drawer-section-header">
              <div>
                <span className="eyebrow">{messages.drawer.reliabilityEyebrow}</span>
                <h3>{messages.drawer.timeoutAndFailover}</h3>
              </div>
              <p className="drawer-section-copy">{messages.drawer.reliabilityCopy}</p>
            </div>

            <div className="drawer-field-grid">
              <label>
                <span>{messages.drawer.timeout}</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={form.timeoutSeconds}
                  onChange={(event) => update('timeoutSeconds', event.target.value)}
                  required
                />
              </label>

              <label>
                <span>{messages.drawer.maxFailures}</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={form.maxFailures}
                  onChange={(event) => update('maxFailures', event.target.value)}
                  required
                />
              </label>

              <label>
                <span>{messages.drawer.cooldown}</span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={form.cooldownSeconds}
                  onChange={(event) => update('cooldownSeconds', event.target.value)}
                  required
                />
              </label>
            </div>
          </section>

          <div className="drawer-footer">
            <button type="button" className="ghost-button" onClick={onClose} disabled={busy}>
              {messages.drawer.cancel}
            </button>
            <button type="submit" className="accent-button" disabled={busy}>
              {busy ? messages.drawer.saving : submitLabel}
            </button>
          </div>
        </form>
      </aside>
    </div>
  )
}
