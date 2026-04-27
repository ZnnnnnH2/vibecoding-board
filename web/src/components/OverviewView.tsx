import {
  Activity,
  ArrowRight,
  Boxes,
  ChevronDown,
  ChevronUp,
  Gauge,
  LoaderCircle,
  ShieldCheck,
  Timer,
  Waves,
} from 'lucide-react'
import { motion } from 'framer-motion'
import { useState } from 'react'

import type { Variants } from 'framer-motion'

import {
  DistributionBarCard,
  DonutCard,
  DualTrendCard,
  LineTrendCard,
} from './MetricsCharts'
import {
  findProviderStats,
  formatCountCompact,
  formatNumber,
  formatPercent,
  formatTimestamp,
  getHealthState,
  getProviderStatus,
  getRequestStateMeta,
  requestHeadline,
  sortProviders,
} from '../format'
import { useI18n } from '../i18n'

import type { DashboardResponse, MetricsResponse, MetricsWindow, TokenUsageResponse, TrafficPreset } from '../types'

type TokenBreakdownEntry = [string, TokenUsageResponse['providers'][string]]


type OverviewViewProps = {
  dashboard: DashboardResponse
  metrics: MetricsResponse | null
  tokenUsage: TokenUsageResponse | null
  metricsWindow: MetricsWindow
  proxyBase: string
  loading: boolean
  onMetricsWindowChange: (window: MetricsWindow) => void
  onNavigate: (view: 'providers' | 'traffic', trafficPreset?: TrafficPreset) => void
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
    },
  },
}

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 20 },
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

function sortTokenBreakdowns(a: TokenBreakdownEntry, b: TokenBreakdownEntry) {
  const tokenDiff = b[1].total_tokens - a[1].total_tokens
  return tokenDiff === 0 ? a[0].localeCompare(b[0]) : tokenDiff
}

export function OverviewView({
  dashboard,
  metrics,
  tokenUsage,
  metricsWindow,
  proxyBase,
  loading,
  onMetricsWindowChange,
  onNavigate,
}: OverviewViewProps) {
  const { locale, messages } = useI18n()
  const [showTokenProviders, setShowTokenProviders] = useState(false)
  const [showTokenModels, setShowTokenModels] = useState(false)
  const sortedProviders = sortProviders(dashboard.providers)
  const recentPreview = dashboard.recent_requests.slice(0, 5)
  const providerTokenEntries = tokenUsage
    ? Object.entries(tokenUsage.providers).sort(sortTokenBreakdowns)
    : []
  const modelTokenEntries = tokenUsage
    ? Object.entries(tokenUsage.models).sort(sortTokenBreakdowns)
    : []
  const stateItems = [
    {
      state: 'success' as const,
      count: metrics?.breakdowns.states.find((item) => item.state === 'success')?.count ?? 0,
      label: messages.requestState.success,
      color: 'var(--success)',
    },
    {
      state: 'interrupted' as const,
      count: metrics?.breakdowns.states.find((item) => item.state === 'interrupted')?.count ?? 0,
      label: messages.requestState.interrupted,
      color: 'var(--warning)',
    },
    {
      state: 'error' as const,
      count: metrics?.breakdowns.states.find((item) => item.state === 'error')?.count ?? 0,
      label: messages.requestState.failed,
      color: 'var(--danger)',
    },
  ]

  return (
    <motion.div 
      className="page-stack"
      variants={containerVariants}
      initial="hidden"
      animate="visible"
    >
      <motion.section variants={itemVariants} className="hero-surface">
        <div className="hero-copy">
          <span className="eyebrow">{messages.overview.eyebrow}</span>
          <h1>{messages.overview.heroTitle}</h1>
          <p>{messages.overview.heroCopy}</p>
        </div>

        <div className="hero-callout">
          <div className="surface-label">{messages.overview.currentEndpoint}</div>
          <strong>{proxyBase}</strong>
          <p>{messages.overview.currentEndpointCopy}</p>
          <button
            type="button"
            className="ghost-button"
            onClick={() => onNavigate('providers')}
          >
            {messages.overview.manageProviders}
            <ArrowRight size={16} />
          </button>
        </div>
      </motion.section>

      <motion.section variants={itemVariants} className="kpi-grid">
        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">{messages.overview.primaryProvider}</span>
            <ShieldCheck size={16} />
          </div>
          <strong>{dashboard.primary_provider ?? messages.app.noSelectedProvider}</strong>
          <p>{messages.overview.primaryProviderCopy}</p>
        </article>

        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">{messages.overview.providers}</span>
            <Boxes size={16} />
          </div>
          <strong>{formatCountCompact(dashboard.providers.length)}</strong>
          <p>{messages.overview.providersCopy}</p>
        </article>

        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">{messages.overview.successRate}</span>
            <Activity size={16} />
          </div>
          <strong>{formatPercent(dashboard.stats.global.success_rate)}</strong>
          <p>{messages.overview.successRateCopy}</p>
        </article>

        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">{messages.overview.avgLatency}</span>
            <Timer size={16} />
          </div>
          <strong>{formatNumber(dashboard.stats.global.average_duration_ms)} ms</strong>
          <p>{messages.overview.avgLatencyCopy}</p>
        </article>

        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">{messages.overview.avgFirstByte}</span>
            <Gauge size={16} />
          </div>
          <strong>{formatNumber(dashboard.stats.global.average_ttfb_ms)} ms</strong>
          <p>{messages.overview.avgFirstByteCopy}</p>
        </article>

        <article className="kpi-card">
          <div className="kpi-head">
            <span className="surface-label">{messages.overview.servedRequests}</span>
            <Waves size={16} />
          </div>
          <strong>{formatCountCompact(dashboard.stats.global.served_requests)}</strong>
          <p>{messages.overview.servedRequestsCopy}</p>
        </article>
      </motion.section>

      {tokenUsage && tokenUsage.total_requests > 0 && (
        <motion.section variants={itemVariants} className="surface-card">
          <div className="section-header">
            <div>
              <span className="eyebrow">{messages.overview.tokenUsageEyebrow}</span>
              <h2>{messages.overview.tokenUsageTitle}</h2>
            </div>
          </div>
          <p className="section-copy">{messages.overview.tokenUsageCopy}</p>

          <div className="kpi-grid token-kpi-grid">
            <article className="kpi-card">
              <span className="surface-label">{messages.overview.totalTokens}</span>
              <strong>{formatCountCompact(tokenUsage.total_tokens)}</strong>
            </article>
            <article className="kpi-card">
              <span className="surface-label">{messages.overview.inputTokens}</span>
              <strong>{formatCountCompact(tokenUsage.input_tokens)}</strong>
            </article>
            <article className="kpi-card">
              <span className="surface-label">{messages.overview.outputTokens}</span>
              <strong>{formatCountCompact(tokenUsage.output_tokens)}</strong>
            </article>
            <article className="kpi-card">
              <span className="surface-label">{messages.overview.totalRequests}</span>
              <strong>{formatCountCompact(tokenUsage.total_requests)}</strong>
            </article>
          </div>

          <div className="token-usage-summary">
            <span>
              {messages.overview.tokenUsageBreakdownSummary(
                formatCountCompact(tokenUsage.requests_with_usage),
                providerTokenEntries.length,
                modelTokenEntries.length,
              )}
            </span>
            {tokenUsage.updated_at ? (
              <span>{messages.overview.tokenUsageUpdatedAt}: {formatTimestamp(tokenUsage.updated_at, locale)}</span>
            ) : null}
          </div>

          <div className="token-disclosure-stack">
            {providerTokenEntries.length > 0 && (
              <div className="token-disclosure">
                <div className="token-disclosure-head">
                  <div>
                    <span className="surface-label">{messages.overview.tokensByProvider}</span>
                    <strong>{messages.overview.tokenUsageProviderCount(providerTokenEntries.length)}</strong>
                  </div>
                  <button
                    type="button"
                    className="ghost-button token-disclosure-button"
                    aria-expanded={showTokenProviders}
                    aria-controls="token-provider-breakdown"
                    onClick={() => setShowTokenProviders((current) => !current)}
                  >
                    {messages.overview.tokenUsageProviderToggle(providerTokenEntries.length, showTokenProviders)}
                    {showTokenProviders ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </div>

                {showTokenProviders ? (
                  <div id="token-provider-breakdown" className="snapshot-table-wrap token-disclosure-panel">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{messages.providers.provider}</th>
                          <th>{messages.overview.totalTokens}</th>
                          <th>{messages.overview.inputTokens}</th>
                          <th>{messages.overview.outputTokens}</th>
                          <th>{messages.overview.totalRequests}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {providerTokenEntries.map(([name, stats]) => (
                          <tr key={name}>
                            <td><strong>{name}</strong></td>
                            <td>{formatCountCompact(stats.total_tokens)}</td>
                            <td>{formatCountCompact(stats.input_tokens)}</td>
                            <td>{formatCountCompact(stats.output_tokens)}</td>
                            <td>{formatCountCompact(stats.requests)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            )}

            {modelTokenEntries.length > 0 && (
              <div className="token-disclosure">
                <div className="token-disclosure-head">
                  <div>
                    <span className="surface-label">{messages.overview.tokensByModel}</span>
                    <strong>{messages.overview.tokenUsageModelCount(modelTokenEntries.length)}</strong>
                  </div>
                  <button
                    type="button"
                    className="ghost-button token-disclosure-button"
                    aria-expanded={showTokenModels}
                    aria-controls="token-model-breakdown"
                    onClick={() => setShowTokenModels((current) => !current)}
                  >
                    {messages.overview.tokenUsageModelToggle(modelTokenEntries.length, showTokenModels)}
                    {showTokenModels ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                  </button>
                </div>

                {showTokenModels ? (
                  <div id="token-model-breakdown" className="snapshot-table-wrap token-disclosure-panel">
                    <table className="data-table">
                      <thead>
                        <tr>
                          <th>{messages.providers.models}</th>
                          <th>{messages.overview.totalTokens}</th>
                          <th>{messages.overview.inputTokens}</th>
                          <th>{messages.overview.outputTokens}</th>
                          <th>{messages.overview.totalRequests}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {modelTokenEntries.map(([name, stats]) => (
                          <tr key={name}>
                            <td><strong>{name}</strong></td>
                            <td>{formatCountCompact(stats.total_tokens)}</td>
                            <td>{formatCountCompact(stats.input_tokens)}</td>
                            <td>{formatCountCompact(stats.output_tokens)}</td>
                            <td>{formatCountCompact(stats.requests)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        </motion.section>
      )}

      <motion.section variants={itemVariants} className="surface-card">
        <div className="section-header">
          <div>
            <span className="eyebrow">{messages.overview.chartsEyebrow}</span>
            <h2>{messages.overview.chartsTitle}</h2>
          </div>

          <div className="window-switch">
            <button
              type="button"
              className={metricsWindow === '24h' ? 'window-switch-active' : ''}
              onClick={() => onMetricsWindowChange('24h')}
            >
              {messages.overview.window24h}
            </button>
            <button
              type="button"
              className={metricsWindow === '7d' ? 'window-switch-active' : ''}
              onClick={() => onMetricsWindowChange('7d')}
            >
              {messages.overview.window7d}
            </button>
          </div>
        </div>

        {metrics == null ? (
          <div className="empty-inline">
            <LoaderCircle size={16} />
            <span>{messages.overview.metricsUnavailable}</span>
          </div>
        ) : (
          <div className="charts-grid">
            <LineTrendCard
              title={messages.overview.requestsTrendTitle}
              description={messages.overview.requestsTrendCopy}
              points={metrics.timeseries.requests}
              latestLabel={messages.overview.latestRequests}
              formatLatestValue={formatCountCompact}
              color="var(--accent)"
              icon="requests"
            />
            <LineTrendCard
              title={messages.overview.tokensTrendTitle}
              description={messages.overview.tokensTrendCopy}
              points={metrics.timeseries.tokens}
              latestLabel={messages.overview.latestTokens}
              formatLatestValue={formatCountCompact}
              color="#0ea5e9"
              icon="tokens"
            />
            <LineTrendCard
              title={messages.overview.durationTrendTitle}
              description={messages.overview.durationTrendCopy}
              points={metrics.timeseries.duration_ms}
              latestLabel={messages.overview.latestDuration}
              color="#8b5cf6"
              icon="duration"
            />
            <LineTrendCard
              title={messages.overview.failoverTrendTitle}
              description={messages.overview.failoverTrendCopy}
              points={metrics.timeseries.failover_requests}
              latestLabel={messages.overview.latestFailovers}
              formatLatestValue={formatCountCompact}
              color="#f97316"
              icon="requests"
            />
            <DualTrendCard
              title={messages.overview.reliabilityTrendTitle}
              description={messages.overview.reliabilityTrendCopy}
              primaryPoints={metrics.timeseries.success_rate}
              primaryLabel={messages.overview.successRate}
              primaryColor="var(--success)"
              secondaryPoints={metrics.timeseries.duration_ms}
              secondaryLabel={messages.overview.avgLatency}
              secondaryColor="var(--warning)"
            />
            <DistributionBarCard
              title={messages.overview.providerLoadTitle}
              description={messages.overview.providerLoadCopy}
              items={metrics.breakdowns.providers}
            />
            <DonutCard
              title={messages.overview.stateDistributionTitle}
              description={messages.overview.stateDistributionCopy}
              items={stateItems}
            />
          </div>
        )}
      </motion.section>

      <motion.section variants={itemVariants} className="split-grid">
        <article className="surface-card">
          <div className="section-header">
            <div>
              <span className="eyebrow">{messages.overview.runtimeEyebrow}</span>
              <h2>{messages.overview.proxyStatus}</h2>
            </div>
            {loading ? <span className="status-dot status-dot-live">{messages.overview.syncing}</span> : <span className="status-dot">{messages.overview.synced}</span>}
          </div>

          <div className="runtime-grid">
            <div className="runtime-card">
              <span className="surface-label">{messages.overview.listenAddress}</span>
              <strong>
                {dashboard.listen_host}:{dashboard.listen_port}
              </strong>
            </div>
            <div className="runtime-card">
              <span className="surface-label">{messages.app.configPath}</span>
              <strong>{dashboard.config_path}</strong>
            </div>
            <div className="runtime-card">
              <span className="surface-label">{messages.overview.lastReload}</span>
              <strong>{formatTimestamp(dashboard.reloaded_at, locale)}</strong>
            </div>
            <div className="runtime-card">
              <span className="surface-label">{messages.overview.usageRows}</span>
              <strong>{formatCountCompact(dashboard.stats.global.requests_with_usage)}</strong>
            </div>
          </div>
        </article>

        <article className="surface-card">
          <div className="section-header">
            <div>
              <span className="eyebrow">{messages.overview.trafficEyebrow}</span>
              <h2>{messages.overview.recentPreview}</h2>
            </div>
            <button
              type="button"
              className="ghost-button"
              onClick={() => onNavigate('traffic')}
            >
              {messages.overview.openTraffic}
              <ArrowRight size={16} />
            </button>
          </div>

          {recentPreview.length === 0 ? (
            <div className="empty-inline">
              <LoaderCircle size={16} />
              <span>{messages.overview.noRequestsYet}</span>
            </div>
          ) : (
            <div className="list-stack">
              {recentPreview.map((request) => {
                const requestState = getRequestStateMeta(request.state, messages)
                return (
                  <button
                    key={request.id}
                    type="button"
                    className="compact-row"
                    onClick={() => onNavigate('traffic', {
                      requestId: request.id,
                      state: request.state,
                      kind: request.request_kind === 'response' ? 'response' : 'chat',
                      search: request.model,
                    })}
                  >
                    <div>
                      <strong>{requestHeadline(request, messages)}</strong>
                      <span>{request.final_provider ?? messages.traffic.noProviderSelected}</span>
                    </div>
                    <div className="compact-row-side">
                      <span className={`pill pill-${requestState.tone}`}>
                        {requestState.label}
                      </span>
                      <small>{formatTimestamp(request.created_at, locale)}</small>
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </article>
      </motion.section>

      <motion.section variants={itemVariants} className="surface-card">
        <div className="section-header">
          <div>
            <span className="eyebrow">{messages.overview.providersEyebrow}</span>
            <h2>{messages.overview.healthSnapshot}</h2>
          </div>
          <button
            type="button"
            className="ghost-button"
            onClick={() => onNavigate('providers')}
          >
            {messages.overview.openProviders}
            <ArrowRight size={16} />
          </button>
        </div>

        <div className="snapshot-table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th>{messages.providers.provider}</th>
                <th>{messages.providers.status}</th>
                <th>{messages.providers.priority}</th>
                <th>{messages.overview.healthcheck}</th>
                <th>{messages.overview.requests}</th>
                <th>{messages.overview.avgLatencyColumn}</th>
                <th>{messages.overview.lastSuccess}</th>
              </tr>
            </thead>
            <tbody>
              {sortedProviders.map((provider) => {
                const status = getProviderStatus(provider, messages)
                const health = getHealthState(provider.healthcheck, messages)
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
                            ? `${provider.healthcheck.model ?? messages.app.noModel} · ${provider.healthcheck.latency_ms ?? messages.app.notAvailable} ms`
                            : messages.overview.noManualCheck}
                        </span>
                      </div>
                    </td>
                    <td>{formatCountCompact(stats?.served_requests ?? 0)}</td>
                    <td>{formatNumber(stats?.average_duration_ms ?? null)} ms</td>
                    <td>{formatTimestamp(provider.last_success_at, locale)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </motion.section>
    </motion.div>
  )
}
