import {
  Activity,
  ArrowRight,
  Boxes,
  Gauge,
  LoaderCircle,
  ShieldCheck,
  Timer,
  Waves,
} from 'lucide-react'

import {
  findProviderStats,
  formatNumber,
  formatPercent,
  formatTimestamp,
  getHealthState,
  getProviderStatus,
  requestHeadline,
  sortProviders,
} from '../format'

import type { DashboardResponse } from '../types'


type OverviewViewProps = {
  dashboard: DashboardResponse
  proxyBase: string
  loading: boolean
  onNavigate: (view: 'providers' | 'traffic') => void
}


export function OverviewView({
  dashboard,
  proxyBase,
  loading,
  onNavigate,
}: OverviewViewProps) {
  const sortedProviders = sortProviders(dashboard.providers)
  const recentPreview = dashboard.recent_requests.slice(0, 5)

  return (
    <div className="page-stack">
      <section className="hero-surface">
        <div className="hero-copy">
          <span className="eyebrow">Overview</span>
          <h1>Local proxy control plane</h1>
          <p>
            One screen for routing health, current primary selection, and recent request behavior
            across your OpenAI-compatible upstream providers.
          </p>
        </div>

        <div className="hero-callout">
          <div className="surface-label">Current endpoint</div>
          <strong>{proxyBase}</strong>
          <p>
            Requests hit the local proxy first. Routing, failover, and runtime config changes are
            applied from here.
          </p>
          <button
            type="button"
            className="ghost-button"
            onClick={() => onNavigate('providers')}
          >
            Manage providers
            <ArrowRight size={16} />
          </button>
        </div>
      </section>

      <section className="kpi-grid">
        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">Primary provider</span>
            <ShieldCheck size={16} />
          </div>
          <strong>{dashboard.primary_provider ?? 'None selected'}</strong>
          <p>Lowest healthy priority currently serving new traffic.</p>
        </article>

        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">Providers</span>
            <Boxes size={16} />
          </div>
          <strong>{dashboard.providers.length}</strong>
          <p>Configured upstream relays available to the proxy runtime.</p>
        </article>

        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">Success rate</span>
            <Activity size={16} />
          </div>
          <strong>{formatPercent(dashboard.stats.global.success_rate)}</strong>
          <p>Computed from recent in-memory request logs.</p>
        </article>

        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">Avg latency</span>
            <Timer size={16} />
          </div>
          <strong>{formatNumber(dashboard.stats.global.average_duration_ms)} ms</strong>
          <p>Total request duration across successfully served traffic.</p>
        </article>

        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">Avg first byte</span>
            <Gauge size={16} />
          </div>
          <strong>{formatNumber(dashboard.stats.global.average_ttfb_ms)} ms</strong>
          <p>How quickly upstreams begin returning tokens or response content.</p>
        </article>

        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">Served requests</span>
            <Waves size={16} />
          </div>
          <strong>{dashboard.stats.global.served_requests}</strong>
          <p>Transient history only. These rows are cleared when the process restarts.</p>
        </article>
      </section>

      <section className="split-grid">
        <article className="surface-card">
          <div className="section-header">
            <div>
              <span className="eyebrow">Runtime</span>
              <h2>Proxy status</h2>
            </div>
            {loading ? <span className="status-dot status-dot-live">Syncing</span> : <span className="status-dot">Synced</span>}
          </div>

          <div className="runtime-grid">
            <div className="runtime-card">
              <span className="surface-label">Listen address</span>
              <strong>
                {dashboard.listen_host}:{dashboard.listen_port}
              </strong>
            </div>
            <div className="runtime-card">
              <span className="surface-label">Config path</span>
              <strong>{dashboard.config_path}</strong>
            </div>
            <div className="runtime-card">
              <span className="surface-label">Last reload</span>
              <strong>{formatTimestamp(dashboard.reloaded_at)}</strong>
            </div>
            <div className="runtime-card">
              <span className="surface-label">Usage rows</span>
              <strong>{dashboard.stats.global.requests_with_usage}</strong>
            </div>
          </div>
        </article>

        <article className="surface-card">
          <div className="section-header">
            <div>
              <span className="eyebrow">Traffic</span>
              <h2>Recent preview</h2>
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={() => onNavigate('traffic')}
            >
              Open traffic
              <ArrowRight size={16} />
            </button>
          </div>

          {recentPreview.length === 0 ? (
            <div className="empty-inline">
              <LoaderCircle size={16} />
              <span>No requests yet. Recent routing records will appear here.</span>
            </div>
          ) : (
            <div className="list-stack">
              {recentPreview.map((request) => (
                <button
                  key={request.id}
                  type="button"
                  className="compact-row"
                  onClick={() => onNavigate('traffic')}
                >
                  <div>
                    <strong>{requestHeadline(request)}</strong>
                    <span>{request.final_provider ?? 'No provider selected'}</span>
                  </div>
                  <div className="compact-row-side">
                    <span className={`pill pill-${request.state === 'success' ? 'emerald' : request.state === 'interrupted' ? 'amber' : 'rose'}`}>
                      {request.state}
                    </span>
                    <small>{formatTimestamp(request.created_at)}</small>
                  </div>
                </button>
              ))}
            </div>
          )}
        </article>
      </section>

      <section className="surface-card">
        <div className="section-header">
          <div>
            <span className="eyebrow">Providers</span>
            <h2>Health snapshot</h2>
          </div>
          <button
            type="button"
            className="ghost-button"
            onClick={() => onNavigate('providers')}
          >
            Open providers
            <ArrowRight size={16} />
          </button>
        </div>

        <div className="snapshot-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>Provider</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Healthcheck</th>
                <th>Requests</th>
                <th>Avg latency</th>
                <th>Last success</th>
              </tr>
            </thead>
            <tbody>
              {sortedProviders.map((provider) => {
                const status = getProviderStatus(provider)
                const health = getHealthState(provider.healthcheck)
                const stats = findProviderStats(dashboard.stats, provider.name)
                return (
                  <tr key={provider.name}>
                    <td>
                      <div className="table-primary">
                        <strong>{provider.name}</strong>
                        <span>{provider.base_url}</span>
                      </div>
                    </td>
                    <td>
                      <span className={`pill pill-${status.tone}`}>{status.label}</span>
                    </td>
                    <td>{provider.priority}</td>
                    <td>
                      <div className="table-primary">
                        <span className={`pill pill-${health.tone}`}>{health.label}</span>
                        <span>
                          {provider.healthcheck.checked_at
                            ? `${provider.healthcheck.model ?? 'no model'} · ${provider.healthcheck.latency_ms ?? 'N/A'} ms`
                            : 'No manual check'}
                        </span>
                      </div>
                    </td>
                    <td>{stats?.served_requests ?? 0}</td>
                    <td>{formatNumber(stats?.average_duration_ms ?? null)} ms</td>
                    <td>{formatTimestamp(provider.last_success_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
