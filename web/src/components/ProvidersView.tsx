import { Search, SlidersHorizontal } from 'lucide-react'
import { useDeferredValue, useState } from 'react'

import {
  findProviderStats,
  formatNumber,
  formatPercent,
  formatTimestamp,
  getHealthState,
  getModelsLabel,
  getProviderStatus,
  sortProviders,
} from '../format'

import type { DashboardResponse, ProviderSummary } from '../types'


type ProviderFilter = 'all' | 'ready' | 'cooling' | 'disabled' | 'unsteady'

type ProvidersViewProps = {
  dashboard: DashboardResponse
  busyAction: string | null
  onCreate: () => void
  onEdit: (provider: ProviderSummary) => void
  onHealthcheck: (provider: ProviderSummary) => void
  onPromote: (provider: ProviderSummary) => void
  onToggle: (provider: ProviderSummary) => void
  onDelete: (provider: ProviderSummary) => void
  onPrioritySave: (provider: ProviderSummary, priority: number) => Promise<boolean>
}


export function ProvidersView({
  dashboard,
  busyAction,
  onCreate,
  onEdit,
  onHealthcheck,
  onPromote,
  onToggle,
  onDelete,
  onPrioritySave,
}: ProvidersViewProps) {
  const [search, setSearch] = useState('')
  const [enabledOnly, setEnabledOnly] = useState(false)
  const [statusFilter, setStatusFilter] = useState<ProviderFilter>('all')
  const deferredSearch = useDeferredValue(search)

  const visibleProviders = sortProviders(dashboard.providers).filter((provider) => {
    const query = deferredSearch.trim().toLowerCase()
    const haystack = `${provider.name} ${provider.base_url} ${provider.models.join(' ')}`.toLowerCase()
    const status = getProviderStatus(provider).label.toLowerCase()
    const matchesSearch = haystack.includes(query)
    const matchesEnabled = !enabledOnly || provider.enabled
    const matchesStatus =
      statusFilter === 'all' ? true : status === statusFilter
    return matchesSearch && matchesEnabled && matchesStatus
  })

  async function commitPriority(provider: ProviderSummary, value: string, input: HTMLInputElement) {
    const normalized = Number.parseInt(value.trim(), 10)
    if (!Number.isFinite(normalized) || normalized < 1) {
      input.value = String(provider.priority)
      return
    }

    if (normalized === provider.priority) {
      input.value = String(provider.priority)
      return
    }

    const saved = await onPrioritySave(provider, normalized)
    if (!saved) {
      input.value = String(provider.priority)
    }
  }

  return (
    <div className="page-stack">
      <section className="surface-card">
        <div className="section-header">
          <div>
            <span className="eyebrow">Providers</span>
            <h2>Routing inventory</h2>
          </div>
          <button type="button" className="accent-button" onClick={onCreate}>
            Add provider
          </button>
        </div>

        <div className="toolbar-row">
          <label className="search-field">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by name, URL, or model"
            />
          </label>

          <label className="toggle-chip">
            <input
              type="checkbox"
              checked={enabledOnly}
              onChange={(event) => setEnabledOnly(event.target.checked)}
            />
            <span>Enabled only</span>
          </label>

          <label className="select-field">
            <SlidersHorizontal size={16} />
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as ProviderFilter)}
            >
              <option value="all">All states</option>
              <option value="ready">Ready</option>
              <option value="cooling">Cooling</option>
              <option value="disabled">Disabled</option>
              <option value="unsteady">Unsteady</option>
            </select>
          </label>
        </div>

        {visibleProviders.length === 0 ? (
          <div className="empty-state compact-empty">
            <h3>No providers match the current filters</h3>
            <p>Clear filters or add a new upstream relay to extend the routing pool.</p>
          </div>
        ) : (
          <div className="table-shell">
            <table className="data-table providers-table">
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Models</th>
                  <th>Health</th>
                  <th>Traffic</th>
                  <th>Reliability</th>
                  <th>Last success</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {visibleProviders.map((provider) => {
                  const status = getProviderStatus(provider)
                  const health = getHealthState(provider.healthcheck)
                  const stats = findProviderStats(dashboard.stats, provider.name)
                  return (
                    <tr key={provider.name}>
                      <td>
                        <div className="table-primary">
                          <div className="table-title-row">
                            <strong>{provider.name}</strong>
                            {dashboard.primary_provider === provider.name ? (
                              <span className="pill pill-primary">Primary</span>
                            ) : null}
                          </div>
                          <span>{provider.base_url}</span>
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">
                          <span className={`pill pill-${status.tone}`}>{status.label}</span>
                          <span>{provider.enabled ? 'Eligible for routing' : 'Ignored by router'}</span>
                        </div>
                      </td>
                      <td>
                        <div className="priority-editor">
                          <input
                            key={`${provider.name}:${provider.priority}`}
                            className="table-priority-input"
                            type="number"
                            min="1"
                            step="1"
                            defaultValue={provider.priority}
                            onBlur={(event) => {
                              void commitPriority(provider, event.currentTarget.value, event.currentTarget)
                            }}
                            onKeyDown={(event) => {
                              if (event.key === 'Enter') {
                                event.preventDefault()
                                event.currentTarget.blur()
                              }
                            }}
                            disabled={busyAction !== null}
                          />
                          {busyAction === `priority:${provider.name}` ? (
                            <span className="table-helper-text">Saving…</span>
                          ) : (
                            <span className="table-helper-text">Blur to apply</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">
                          <strong>{getModelsLabel(provider)}</strong>
                          <span>
                            {provider.healthcheck_model
                              ? `Healthcheck: ${provider.healthcheck_model}`
                              : provider.supports_all_models
                                ? 'Set a healthcheck model for wildcard checks'
                                : 'Uses first explicit model by default'}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">
                          <span className={`pill pill-${health.tone}`}>{health.label}</span>
                          <span>
                            {provider.healthcheck.checked_at
                              ? `${provider.healthcheck.model ?? 'no model'} · ${provider.healthcheck.latency_ms ?? 'N/A'} ms`
                              : 'No manual check yet'}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">
                          <strong>{stats?.served_requests ?? 0} requests</strong>
                          <span>{formatPercent(stats?.success_rate ?? null)} success</span>
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">
                          <strong>
                            {provider.consecutive_failures}/{provider.max_failures} failures
                          </strong>
                          <span>
                            {formatNumber(stats?.average_duration_ms ?? null)} ms avg · {provider.cooldown_seconds}s cooldown
                          </span>
                        </div>
                      </td>
                      <td>{formatTimestamp(provider.last_success_at)}</td>
                      <td>
                        <div className="action-cluster">
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => onEdit(provider)}
                            disabled={busyAction !== null}
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => onHealthcheck(provider)}
                            disabled={busyAction !== null}
                          >
                            {busyAction === `health:${provider.name}` ? 'Checking…' : 'Check'}
                          </button>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => onPromote(provider)}
                            disabled={busyAction !== null || dashboard.primary_provider === provider.name}
                          >
                            {busyAction === `promote:${provider.name}` ? 'Switching…' : 'Primary'}
                          </button>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => onToggle(provider)}
                            disabled={busyAction !== null}
                          >
                            {busyAction === `toggle:${provider.name}` ? 'Saving…' : provider.enabled ? 'Disable' : 'Enable'}
                          </button>
                          <button
                            type="button"
                            className="table-action danger"
                            onClick={() => onDelete(provider)}
                            disabled={busyAction !== null}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
