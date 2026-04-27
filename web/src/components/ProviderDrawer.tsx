import type { FocusEvent, FormEvent, KeyboardEvent } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Network, Route, ShieldAlert, X, Save, Activity } from 'lucide-react'

import { useI18n } from '../i18n'
import type { ProviderFormState } from '../types'

type ProviderDrawerProps = {
  open: boolean
  mode: 'create' | 'edit'
  busy: boolean
  form: ProviderFormState
  onClose: () => void
  onChange: (next: ProviderFormState) => void
  onSubmit: (form: ProviderFormState) => void
  onAutoSave: (form: ProviderFormState) => void
}

export function ProviderDrawer({
  open,
  mode,
  busy,
  form,
  onClose,
  onChange,
  onSubmit,
  onAutoSave,
}: ProviderDrawerProps) {
  const { messages } = useI18n()
  const autoSaveEnabled = mode === 'edit'
  const submitLabel = mode === 'create' ? messages.drawer.addProvider : messages.drawer.saveChanges

  function update<K extends keyof ProviderFormState>(key: K, value: ProviderFormState[K]) {
    onChange({
      ...form,
      [key]: value,
    })
  }

  function commit<K extends keyof ProviderFormState>(key: K, value: ProviderFormState[K]) {
    const nextForm = {
      ...form,
      [key]: value,
    }
    onChange(nextForm)
    if (autoSaveEnabled) {
      onAutoSave(nextForm)
    }
  }

  function commitCurrentForm() {
    if (autoSaveEnabled) {
      onAutoSave(form)
    }
  }

  function handleGroupedBlur(event: FocusEvent<HTMLElement>) {
    const nextFocused =
      event.relatedTarget instanceof HTMLElement ? event.relatedTarget : null
    if (nextFocused && event.currentTarget.contains(nextFocused)) {
      return
    }
    commitCurrentForm()
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (mode === 'create') {
      onSubmit(form)
    }
  }

  function blurOnEnter(event: KeyboardEvent<HTMLInputElement>) {
    if (autoSaveEnabled && event.key === 'Enter') {
      event.preventDefault()
      event.currentTarget.blur()
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="drawer-backdrop"
          role="presentation"
          onClick={() => { if (!busy) onClose() }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
        >
          <motion.aside
            className="drawer-panel"
            onClick={(e) => e.stopPropagation()}
            initial={{ x: '100%', opacity: 0.5 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: '100%', opacity: 0 }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
          >
            <div className="drawer-header">
              <div>
                <span className="eyebrow">{mode === 'create' ? messages.drawer.newUpstream : messages.drawer.editUpstream}</span>
                <h2>{mode === 'create' ? messages.drawer.addProvider : messages.drawer.refineProviderDetails}</h2>
              </div>
              <button type="button" className="ghost-button" onClick={onClose} disabled={busy} style={{ width: '42px', height: '42px', padding: 0 }}>
                <X size={20} />
              </button>
            </div>

            <form className="drawer-form" onSubmit={handleSubmit}>
              <section className="drawer-section">
                <div className="drawer-section-header" style={{ display: 'flex', alignItems: 'flex-start', gap: '0.8rem' }}>
                  <div style={{ flexShrink: 0, padding: '0.5rem', background: 'var(--surface)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
                    <Network size={20} style={{ color: 'var(--accent)' }} />
                  </div>
                  <div>
                    <span className="eyebrow">{messages.drawer.identityEyebrow}</span>
                    <h3>{messages.drawer.connectionDetails}</h3>
                    <p className="drawer-section-copy">{messages.drawer.identityCopy}</p>
                  </div>
                </div>

                <div className="drawer-field-grid">
                  <label>
                    <span>{messages.drawer.name}</span>
                    <input
                      value={form.name}
                      onChange={(event) => update('name', event.target.value)}
                      onBlur={(event) => commit('name', event.currentTarget.value)}
                      onKeyDown={blurOnEnter}
                      placeholder={messages.drawer.namePlaceholder}
                      disabled={busy}
                      required
                    />
                    <small className="field-hint">{messages.drawer.nameHint}</small>
                  </label>

                  <label>
                    <span>{messages.drawer.baseUrl}</span>
                    <input
                      value={form.baseUrl}
                      onChange={(event) => update('baseUrl', event.target.value)}
                      onBlur={(event) => commit('baseUrl', event.currentTarget.value)}
                      onKeyDown={blurOnEnter}
                      placeholder={messages.drawer.baseUrlPlaceholder}
                      disabled={busy}
                      required
                    />
                    <small className="field-hint">{messages.drawer.baseUrlHint}</small>
                  </label>

                  <label className="drawer-field-span">
                    <span>{messages.drawer.apiKey}</span>
                    <input
                      type="password"
                      value={form.apiKey}
                      onChange={(event) => update('apiKey', event.target.value)}
                      onBlur={(event) => commit('apiKey', event.currentTarget.value)}
                      onKeyDown={blurOnEnter}
                      placeholder={mode === 'edit' ? messages.drawer.apiKeyEditPlaceholder : messages.drawer.apiKeyCreatePlaceholder}
                      disabled={busy}
                      required={mode === 'create'}
                    />
                    <small className="field-hint">{messages.drawer.apiKeyHint}</small>
                  </label>
                </div>

                <label className="toggle-switch-wrapper" onBlur={handleGroupedBlur}>
                  <div className="toggle-switch-info">
                    <strong>{messages.drawer.enableAfterSave}</strong>
                  </div>
                  <div className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={form.enabled}
                      onChange={(event) => update('enabled', event.target.checked)}
                      disabled={busy}
                    />
                    <span className="toggle-slider"></span>
                  </div>
                </label>

                <label className="toggle-switch-wrapper" onBlur={handleGroupedBlur}>
                  <div className="toggle-switch-info">
                    <strong>{messages.drawer.responsesWebSocket}</strong>
                    <span>{messages.drawer.responsesWebSocketHint}</span>
                  </div>
                  <div className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={form.supportsResponsesWebsocket}
                      onChange={(event) => update('supportsResponsesWebsocket', event.target.checked)}
                      disabled={busy}
                    />
                    <span className="toggle-slider"></span>
                  </div>
                </label>
              </section>

              <section className="drawer-section">
                <div className="drawer-section-header" style={{ display: 'flex', alignItems: 'flex-start', gap: '0.8rem' }}>
                  <div style={{ flexShrink: 0, padding: '0.5rem', background: 'var(--surface)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
                    <Route size={20} style={{ color: 'var(--accent)' }} />
                  </div>
                  <div>
                    <span className="eyebrow">{messages.drawer.routingEyebrow}</span>
                    <h3>{messages.drawer.selectionRules}</h3>
                    <p className="drawer-section-copy">{messages.drawer.routingCopy}</p>
                  </div>
                </div>

                <div className="drawer-field-grid">
                  <label>
                    <span>{messages.drawer.priority}</span>
                    <input
                      type="number"
                      step="1"
                      value={form.priority}
                      onChange={(event) => update('priority', event.target.value)}
                      onBlur={(event) => commit('priority', event.currentTarget.value)}
                      onKeyDown={blurOnEnter}
                      disabled={busy}
                      required
                    />
                    <small className="field-hint">{messages.drawer.priorityHint}</small>
                  </label>

                  <label>
                    <span>{messages.drawer.healthcheckModel}</span>
                    <input
                      value={form.healthcheckModel}
                      onChange={(event) => update('healthcheckModel', event.target.value)}
                      onBlur={(event) => commit('healthcheckModel', event.currentTarget.value)}
                      onKeyDown={blurOnEnter}
                      placeholder={form.modelMode === 'all' ? messages.drawer.wildcardPlaceholder : messages.drawer.healthcheckPlaceholder}
                      disabled={busy}
                    />
                    <small className="field-hint">{messages.drawer.healthcheckHint}</small>
                  </label>
                </div>

                <div className="segment-control" onBlur={handleGroupedBlur}>
                  <button
                    type="button"
                    className={form.modelMode === 'all' ? 'segment-active' : ''}
                    onClick={() => update('modelMode', 'all')}
                    disabled={busy}
                  >
                    {messages.drawer.allModels}
                  </button>
                  <button
                    type="button"
                    className={form.modelMode === 'explicit' ? 'segment-active' : ''}
                    onClick={() => update('modelMode', 'explicit')}
                    disabled={busy}
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
                      onBlur={(event) => commit('modelText', event.currentTarget.value)}
                      placeholder={messages.drawer.modelsPlaceholder}
                      disabled={busy}
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
                <div className="drawer-section-header" style={{ display: 'flex', alignItems: 'flex-start', gap: '0.8rem' }}>
                  <div style={{ flexShrink: 0, padding: '0.5rem', background: 'var(--surface)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
                    <ShieldAlert size={20} style={{ color: 'var(--accent)' }} />
                  </div>
                  <div>
                    <span className="eyebrow">{messages.drawer.reliabilityEyebrow}</span>
                    <h3>{messages.drawer.timeoutAndFailover}</h3>
                    <p className="drawer-section-copy">{messages.drawer.reliabilityCopy}</p>
                  </div>
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
                      onBlur={(event) => commit('timeoutSeconds', event.currentTarget.value)}
                      onKeyDown={blurOnEnter}
                      disabled={busy}
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
                      onBlur={(event) => commit('maxFailures', event.currentTarget.value)}
                      onKeyDown={blurOnEnter}
                      disabled={busy}
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
                      onBlur={(event) => commit('cooldownSeconds', event.currentTarget.value)}
                      onKeyDown={blurOnEnter}
                      disabled={busy}
                      required
                    />
                  </label>
                </div>

                <label className="toggle-switch-wrapper" onBlur={handleGroupedBlur}>
                  <div className="toggle-switch-info">
                    <strong>{messages.drawer.alwaysAlive}</strong>
                    <span>{messages.drawer.alwaysAliveHint}</span>
                  </div>
                  <div className="toggle-switch">
                    <input
                      type="checkbox"
                      checked={form.alwaysAlive}
                      onChange={(event) => update('alwaysAlive', event.target.checked)}
                      disabled={busy}
                    />
                    <span className="toggle-slider"></span>
                  </div>
                </label>
              </section>

              <div className="drawer-footer">
                <button type="button" className="ghost-button" onClick={onClose} disabled={busy}>
                  {autoSaveEnabled ? messages.drawer.close : messages.drawer.cancel}
                </button>
                {autoSaveEnabled ? (
                  <span className="section-caption">
                    {busy ? messages.drawer.saving : messages.drawer.blurToApply}
                  </span>
                ) : (
                  <button type="submit" className="accent-button" disabled={busy}>
                    {busy ? <Activity size={18} className="spin-icon" /> : <Save size={18} />}
                    {busy ? messages.drawer.saving : submitLabel}
                  </button>
                )}
              </div>
            </form>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
