import { Search, SlidersHorizontal } from 'lucide-react'
import { useDeferredValue, useState } from 'react'
import { motion } from 'framer-motion'

import type { Variants } from 'framer-motion'

import {
  findProviderStats,
  formatNumber,
  formatPercent,
  formatTimestamp,
  getHealthState,
  getProviderRoutingHint,
  getModelsLabel,
  getProviderStatus,
  sortProviders,
} from '../format'
import { useI18n } from '../i18n'

import { DropdownSelect } from './DropdownSelect'

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
  onToggleAlwaysAlive: (provider: ProviderSummary) => void
  onDelete: (provider: ProviderSummary) => void
  onPrioritySave: (provider: ProviderSummary, priority: number) => Promise<boolean>
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

export function ProvidersView({
  dashboard,
  busyAction,
  onCreate,
  onEdit,
  onHealthcheck,
  onPromote,
  onToggle,
  onToggleAlwaysAlive,
  onDelete,
  onPrioritySave,
}: ProvidersViewProps) {
  const { locale, messages } = useI18n()
  const [search, setSearch] = useState('')
  const [enabledOnly, setEnabledOnly] = useState(false)
  const [statusFilter, setStatusFilter] = useState<ProviderFilter>('all')
  const deferredSearch = useDeferredValue(search)

  const visibleProviders = sortProviders(dashboard.providers).filter((provider) => {
    const query = deferredSearch.trim().toLowerCase()
    const haystack = `${provider.name} ${provider.base_url} ${provider.models.join(' ')}`.toLowerCase()
    const status = getProviderStatus(provider, messages).key
    const matchesSearch = haystack.includes(query)
    const matchesEnabled = !enabledOnly || provider.enabled
    const matchesStatus =
      statusFilter === 'all' ? true : status === statusFilter
    return matchesSearch && matchesEnabled && matchesStatus
  })

  async function commitPriority(provider: ProviderSummary, value: string, input: HTMLInputElement) {
    const normalized = Number.parseInt(value.trim(), 10)
    if (!Number.isFinite(normalized)) {
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
    <motion.div 
      className="page-stack"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      <motion.section variants={itemVariants} className="surface-card">
        <div className="section-header">
          <div>
            <span className="eyebrow">{messages.providers.eyebrow}</span>
            <h2>{messages.providers.title}</h2>
          </div>
          <button type="button" className="accent-button" onClick={onCreate}>
            {messages.app.addProvider}
          </button>
        </div>

        <div className="toolbar-row">
          <label className="search-field">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={messages.providers.searchPlaceholder}
            />
          </label>

          <label className="toggle-chip">
            <input
              type="checkbox"
              checked={enabledOnly}
              onChange={(event) => setEnabledOnly(event.target.checked)}
            />
            <span>{messages.providers.enabledOnly}</span>
          </label>

          <DropdownSelect
            value={statusFilter}
            onChange={(val) => setStatusFilter(val as ProviderFilter)}
            options={[
              { value: 'all', label: messages.providers.allStates },
              { value: 'ready', label: messages.providers.ready },
              { value: 'cooling', label: messages.providers.cooling },
              { value: 'disabled', label: messages.providers.disabled },
              { value: 'unsteady', label: messages.providers.unsteady },
            ]}
            icon={<SlidersHorizontal size={16} />}
          />
        </div>

        {visibleProviders.length === 0 ? (
          <div className="empty-state compact-empty">
            <h3>{messages.providers.emptyTitle}</h3>
            <p>{messages.providers.emptyCopy}</p>
          </div>
        ) : (
          <div className="table-shell">
            <table className="data-table providers-table">
              <thead>
                <tr>
                  <th>{messages.providers.provider}</th>
                  <th>{messages.providers.status}</th>
                  <th>{messages.providers.priority}</th>
                  <th>{messages.providers.models}</th>
                  <th>{messages.providers.health}</th>
                  <th>{messages.providers.traffic}</th>
                  <th>{messages.providers.reliability}</th>
                  <th>{messages.providers.lastSuccess}</th>
                  <th>{messages.providers.actions}</th>
                </tr>
              </thead>
              <tbody>
                {visibleProviders.map((provider) => {
                  const status = getProviderStatus(provider, messages)
                  const health = getHealthState(provider.healthcheck, messages)
                  const stats = findProviderStats(dashboard.stats, provider.name)
                  return (
                    <tr key={provider.name}>
                      <td>
                        <div className="table-primary">
                          <div className="table-title-row">
                            <strong>{provider.name}</strong>
                            {dashboard.primary_provider === provider.name ? (
                              <span className="pill pill-preferred">{messages.providers.primary}</span>
                            ) : null}
                          </div>
                          <span>{provider.base_url}</span>
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">
                          <span className={`pill pill-${status.tone}`}>{status.label}</span>
                          <span>{getProviderRoutingHint(provider, messages)}</span>
                        </div>
                      </td>
                      <td>
                        <div className="priority-editor">
                          <input
                            key={`${provider.name}:${provider.priority}`}
                            className="table-priority-input"
                            type="number"
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
                            <span className="table-helper-text">{messages.providers.saving}</span>
                          ) : (
                            <span className="table-helper-text">{messages.providers.blurToApply}</span>
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">
                          <strong>{getModelsLabel(provider, messages)}</strong>
                          <span>
                            {provider.healthcheck_model
                              ? messages.providers.healthcheckLabel(provider.healthcheck_model)
                              : provider.supports_all_models
                                ? messages.providers.wildcardHealthHint
                                : messages.providers.firstExplicitModelHint}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">
                          <span className={`pill pill-${health.tone}`}>{health.label}</span>
                          <span>
                            {provider.healthcheck.checked_at
                              ? `${provider.healthcheck.model ?? messages.app.noModel} · ${provider.healthcheck.latency_ms ?? messages.app.notAvailable} ms`
                              : messages.providers.noManualCheckYet}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">
                          <strong>{messages.providers.requestsCount(stats?.served_requests ?? 0)}</strong>
                          <span>{formatPercent(stats?.success_rate ?? null)} {messages.providers.successSuffix}</span>
                        </div>
                      </td>
                      <td>
                        <div className="table-primary">
                          <strong>
                            {messages.providers.failuresCount(provider.consecutive_failures, provider.max_failures)}
                          </strong>
                          <span>
                            {provider.always_alive
                              ? messages.providers.avgWithAlwaysAlive(formatNumber(stats?.average_duration_ms ?? null))
                              : messages.providers.avgWithCooldown(formatNumber(stats?.average_duration_ms ?? null), provider.cooldown_seconds)}
                          </span>
                        </div>
                      </td>
                      <td>{formatTimestamp(provider.last_success_at, locale)}</td>
                      <td>
                        <div className="action-cluster">
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => onEdit(provider)}
                            disabled={busyAction !== null}
                          >
                            {messages.providers.edit}
                          </button>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => onHealthcheck(provider)}
                            disabled={busyAction !== null}
                          >
                            {busyAction === `health:${provider.name}` ? messages.providers.checking : messages.providers.check}
                          </button>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => onPromote(provider)}
                            disabled={busyAction !== null || dashboard.primary_provider === provider.name}
                          >
                            {busyAction === `promote:${provider.name}` ? messages.providers.switching : messages.providers.makePrimary}
                          </button>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => onToggle(provider)}
                            disabled={busyAction !== null}
                          >
                            {busyAction === `toggle:${provider.name}` ? messages.providers.saving : provider.enabled ? messages.providers.disable : messages.providers.enable}
                          </button>
                          <button
                            type="button"
                            className="table-action"
                            onClick={() => onToggleAlwaysAlive(provider)}
                            disabled={busyAction !== null}
                          >
                            {busyAction === `always-alive:${provider.name}` ? messages.providers.saving : provider.always_alive ? messages.providers.disableAlwaysAlive : messages.providers.alwaysAlive}
                          </button>
                          <button
                            type="button"
                            className="table-action danger"
                            onClick={() => onDelete(provider)}
                            disabled={busyAction !== null}
                          >
                            {messages.providers.delete}
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
      </motion.section>
    </motion.div>
  )
}
