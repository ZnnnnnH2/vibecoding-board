import type { FormEvent } from 'react'

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
  const submitLabel = mode === 'create' ? 'Add provider' : 'Save changes'

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
            <span className="eyebrow">{mode === 'create' ? 'New upstream' : 'Edit upstream'}</span>
            <h2>{mode === 'create' ? 'Add a provider' : 'Refine provider details'}</h2>
          </div>
          <button type="button" className="ghost-button" onClick={onClose} disabled={busy}>
            Close
          </button>
        </div>

        <form className="drawer-form" onSubmit={handleSubmit}>
          <section className="drawer-section">
            <div className="drawer-section-header">
              <div>
                <span className="eyebrow">Identity</span>
                <h3>Connection details</h3>
              </div>
              <p className="drawer-section-copy">
                These values define the upstream relay and the credential this proxy should use.
              </p>
            </div>

            <div className="drawer-field-grid">
              <label>
                <span>Name</span>
                <input
                  value={form.name}
                  onChange={(event) => update('name', event.target.value)}
                  placeholder="relay_primary"
                  required
                />
                <small className="field-hint">Stable identifier shown in the dashboard and routing logs.</small>
              </label>

              <label>
                <span>Base URL</span>
                <input
                  value={form.baseUrl}
                  onChange={(event) => update('baseUrl', event.target.value)}
                  placeholder="https://relay.example.com/v1"
                  required
                />
                <small className="field-hint">Use the upstream API root, usually ending with `/v1`.</small>
              </label>

              <label className="drawer-field-span">
                <span>API key</span>
                <input
                  value={form.apiKey}
                  onChange={(event) => update('apiKey', event.target.value)}
                  placeholder={mode === 'edit' ? 'Leave blank to keep existing key' : 'sk-... or env:VAR_NAME'}
                  required={mode === 'create'}
                />
                <small className="field-hint">
                  Supports direct secrets or environment references such as `env:RELAY_A_API_KEY`.
                </small>
              </label>
            </div>

            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) => update('enabled', event.target.checked)}
              />
              <span>Enable this provider immediately after save</span>
            </label>
          </section>

          <section className="drawer-section">
            <div className="drawer-section-header">
              <div>
                <span className="eyebrow">Routing</span>
                <h3>Selection rules</h3>
              </div>
              <p className="drawer-section-copy">
                Lower priority numbers win. Model scope controls which requests can route here.
              </p>
            </div>

            <div className="drawer-field-grid">
              <label>
                <span>Priority</span>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={form.priority}
                  onChange={(event) => update('priority', event.target.value)}
                  required
                />
                <small className="field-hint">Example: `10` before `20`.</small>
              </label>

              <label>
                <span>Healthcheck model</span>
                <input
                  value={form.healthcheckModel}
                  onChange={(event) => update('healthcheckModel', event.target.value)}
                  placeholder={form.modelMode === 'all' ? 'Required for wildcard providers' : 'Optional override'}
                />
                <small className="field-hint">
                  Used by manual checks when the provider does not expose an explicit model list.
                </small>
              </label>
            </div>

            <div className="segment-control">
              <button
                type="button"
                className={form.modelMode === 'all' ? 'segment-active' : ''}
                onClick={() => update('modelMode', 'all')}
              >
                All models
              </button>
              <button
                type="button"
                className={form.modelMode === 'explicit' ? 'segment-active' : ''}
                onClick={() => update('modelMode', 'explicit')}
              >
                Explicit list
              </button>
            </div>

            {form.modelMode === 'explicit' ? (
              <label>
                <span>Models</span>
                <textarea
                  rows={6}
                  value={form.modelText}
                  onChange={(event) => update('modelText', event.target.value)}
                  placeholder={'One model per line\nexample: gpt-4.1\ngpt-4o-mini'}
                  required
                />
                <small className="field-hint">One model per line. Only listed models will route here.</small>
              </label>
            ) : (
              <div className="form-hint-panel">
                <span className="meta-label">Wildcard routing</span>
                <p>This provider can serve any incoming model name. Set a healthcheck model for manual tests.</p>
              </div>
            )}
          </section>

          <section className="drawer-section">
            <div className="drawer-section-header">
              <div>
                <span className="eyebrow">Reliability</span>
                <h3>Timeout and failover</h3>
              </div>
              <p className="drawer-section-copy">
                These values control when the proxy marks an upstream unhealthy and how long it waits to retry.
              </p>
            </div>

            <div className="drawer-field-grid">
              <label>
                <span>Timeout (seconds)</span>
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
                <span>Max failures</span>
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
                <span>Cooldown (seconds)</span>
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
              Cancel
            </button>
            <button type="submit" className="accent-button" disabled={busy}>
              {busy ? 'Saving...' : submitLabel}
            </button>
          </div>
        </form>
      </aside>
    </div>
  )
}
