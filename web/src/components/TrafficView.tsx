import { Fragment, useDeferredValue, useEffect, useState, useMemo, memo } from 'react'
import { Check, ChevronDown, ChevronUp, Copy, RotateCcw, Search } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'

import type { Variants } from 'framer-motion'

import {
  formatCountCompact,
  formatTimestamp,
  getRequestStateMeta,
  requestHeadline,
} from '../format'
import { useI18n } from '../i18n'
import type { AppMessages } from '../i18n'

import { DropdownSelect } from './DropdownSelect'

import type { RecentRequest, RequestKindFilter, RequestState, TrafficPreset } from '../types'


type RequestStateFilter = 'all' | RequestState
type TrafficDebugFilter = 'all' | 'has_error' | 'failover' | 'retry' | 'sticky'
type RowLimit = 10 | 50
type CopyState = { requestId: string; state: 'copied' | 'failed' } | null

type TrafficViewProps = {
  requests: RecentRequest[]
  preset: TrafficPreset | null
}

const DEFAULT_ROW_LIMIT: RowLimit = 10
const ROW_LIMIT_STORAGE_KEY = 'vibecoding-board:traffic-row-limit'

function isRowLimit(value: number): value is RowLimit {
  return value === 10 || value === 50
}

function readStoredRowLimit(): RowLimit {
  if (typeof window === 'undefined') {
    return DEFAULT_ROW_LIMIT
  }

  try {
    const storedValue = window.localStorage.getItem(ROW_LIMIT_STORAGE_KEY)
    const parsedValue = Number(storedValue)
    return isRowLimit(parsedValue) ? parsedValue : DEFAULT_ROW_LIMIT
  } catch {
    return DEFAULT_ROW_LIMIT
  }
}

function requestHasFailover(request: RecentRequest): boolean {
  return request.attempts.some((attempt) => attempt.next_action === 'failover_next_provider')
}

function requestHasRetry(request: RecentRequest): boolean {
  return request.attempts.some((attempt) => attempt.next_action === 'retry_same_provider')
}

function requestHasStickyOrTurnState(request: RecentRequest): boolean {
  return Boolean(
    request.sticky_provider ||
      request.turn_state_token_present ||
      request.turn_state_status ||
      request.attempts.some((attempt) => attempt.sticky),
  )
}

function requestHasError(request: RecentRequest): boolean {
  return request.state === 'error' || Boolean(request.error)
}

function formatDebugValue(value: string | number | boolean | null | undefined): string {
  if (value == null || value === '') {
    return 'N/A'
  }
  return String(value)
}

function formatUsageDebug(request: RecentRequest): string {
  if (!request.usage) {
    return 'N/A'
  }
  return [
    `input=${formatDebugValue(request.usage.input_tokens)}`,
    `output=${formatDebugValue(request.usage.output_tokens)}`,
    `total=${formatDebugValue(request.usage.total_tokens)}`,
  ].join(', ')
}

function buildRequestDebugSummary(request: RecentRequest): string {
  const lines = [
    `request_id=${request.id}`,
    `created_at=${request.created_at}`,
    `kind=${request.request_kind}`,
    `model=${request.model}`,
    `endpoint=${request.endpoint}`,
    `stream=${request.stream}`,
    `state=${request.state}`,
    `status_code=${formatDebugValue(request.status_code)}`,
    `duration_ms=${formatDebugValue(request.duration_ms)}`,
    `ttfb_ms=${formatDebugValue(request.ttfb_ms)}`,
    `final_provider=${formatDebugValue(request.final_provider)}`,
    `final_url=${formatDebugValue(request.final_url)}`,
    `northbound_transport=${formatDebugValue(request.northbound_transport)}`,
    `southbound_transport=${formatDebugValue(request.southbound_transport)}`,
    `sticky_provider=${formatDebugValue(request.sticky_provider)}`,
    `fallback_reason=${formatDebugValue(request.fallback_reason)}`,
    `turn_state_token_present=${request.turn_state_token_present}`,
    `turn_state_status=${formatDebugValue(request.turn_state_status)}`,
    `usage=${formatUsageDebug(request)}`,
    `error=${formatDebugValue(request.error)}`,
    `attempts=${request.attempts.length}`,
  ]

  for (const [index, attempt] of request.attempts.entries()) {
    lines.push(
      [
        `attempt_${index + 1}:`,
        `provider=${attempt.provider}`,
        `url=${attempt.url}`,
        `outcome=${attempt.outcome}`,
        `status_code=${formatDebugValue(attempt.status_code)}`,
        `retryable=${attempt.retryable}`,
        `provider_attempt=${attempt.provider_attempt}`,
        `next_action=${attempt.next_action}`,
        `transport=${attempt.transport}`,
        `sticky=${attempt.sticky}`,
        `fallback_reason=${formatDebugValue(attempt.fallback_reason)}`,
      ].join(' '),
    )
  }

  return lines.join('\n')
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

const TrafficRow = memo(function TrafficRow({
  request,
  expanded,
  copyState,
  locale,
  messages,
  onToggleExpand,
  onCopyDebug,
}: {
  request: RecentRequest
  expanded: boolean
  copyState: CopyState
  locale: string
  messages: AppMessages
  onToggleExpand: () => void
  onCopyDebug: (request: RecentRequest) => void
}) {
  const requestState = getRequestStateMeta(request.state, messages)
  const hasFailover = requestHasFailover(request)
  const hasRetry = requestHasRetry(request)
  const hasSticky = requestHasStickyOrTurnState(request)
  const hasError = requestHasError(request)
  const requestCopyState = copyState?.requestId === request.id ? copyState.state : null

  function describeNextAction(nextAction: RecentRequest['attempts'][number]['next_action']): string {
    if (nextAction === 'retry_same_provider') {
      return messages.traffic.retrySameProvider
    }
    if (nextAction === 'return_to_client') {
      return messages.traffic.returnToClient
    }
    return messages.traffic.failoverNextProvider
  }

  return (
    <Fragment>
      <motion.tr
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2 }}
      >
        <td>
          <button
            type="button"
            className="expand-button"
            onClick={onToggleExpand}
            aria-label={expanded ? messages.traffic.collapseDetails : messages.traffic.expandDetails}
          >
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </td>
        <td>
          <div className="table-primary">
            <strong>{requestHeadline(request, messages)}</strong>
            <span>{request.final_url ?? request.endpoint}</span>
            <div className="traffic-row-tags">
              <span className="mini-chip">{messages.traffic.attemptCount(request.attempts.length)}</span>
              {request.status_code != null ? (
                <span className="mini-chip">{messages.traffic.statusCodeTag(request.status_code)}</span>
              ) : null}
              {hasRetry ? <span className="mini-chip mini-chip-amber">{messages.traffic.retryTag}</span> : null}
              {hasFailover ? <span className="mini-chip mini-chip-rose">{messages.traffic.failoverTag}</span> : null}
              {hasSticky ? <span className="mini-chip mini-chip-blue">{messages.traffic.stickyTag}</span> : null}
              {hasError ? <span className="mini-chip mini-chip-rose">{messages.traffic.errorTag}</span> : null}
            </div>
          </div>
        </td>
        <td>
          <div className="table-primary">
            <strong>{request.final_provider ?? messages.traffic.noProviderSelected}</strong>
            <span>{request.southbound_transport ?? messages.traffic.noTransport}</span>
          </div>
        </td>
        <td>
          <span className={`pill pill-${requestState.tone}`}>
            {requestState.label}
          </span>
        </td>
        <td>{request.duration_ms ?? messages.app.notAvailable} ms</td>
        <td>{request.ttfb_ms ?? messages.app.notAvailable} ms</td>
        <td>{formatTimestamp(request.created_at, locale)}</td>
      </motion.tr>
      {expanded ? (
        <motion.tr
          className="expanded-row"
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.2 }}
        >
          <td colSpan={7}>
            <div className="expanded-panel">
              <div className="traffic-detail-header">
                <div>
                  <span className="surface-label">{messages.traffic.requestId}</span>
                  <strong>{request.id}</strong>
                </div>
                <button
                  type="button"
                  className="ghost-button traffic-copy-button"
                  onClick={() => onCopyDebug(request)}
                >
                  {requestCopyState === 'copied' ? <Check size={16} /> : <Copy size={16} />}
                  {requestCopyState === 'copied'
                    ? messages.traffic.copiedDebug
                    : requestCopyState === 'failed'
                      ? messages.traffic.copyFailed
                      : messages.traffic.copyDebug}
                </button>
              </div>

              <div className="expanded-grid">
                <div className="expanded-card">
                  <span className="surface-label">{messages.traffic.endpoint}</span>
                  <strong>{request.endpoint}</strong>
                </div>
                <div className="expanded-card">
                  <span className="surface-label">{messages.traffic.mode}</span>
                  <strong>{request.stream ? messages.traffic.streaming : messages.traffic.standard}</strong>
                </div>
                <div className="expanded-card">
                  <span className="surface-label">{messages.traffic.httpStatus}</span>
                  <strong>{request.status_code ?? messages.app.notAvailable}</strong>
                </div>
                <div className="expanded-card">
                  <span className="surface-label">{messages.traffic.usage}</span>
                  <strong>
                    {request.usage
                      ? `${formatCountCompact(request.usage.input_tokens, messages.app.notAvailable)} / ${formatCountCompact(request.usage.output_tokens, messages.app.notAvailable)} / ${formatCountCompact(request.usage.total_tokens, messages.app.notAvailable)}`
                      : messages.traffic.noUsageFields}
                  </strong>
                </div>
              </div>

              <div className="expanded-block routing-trace-block">
                <span className="surface-label">{messages.traffic.routingTrace}</span>
                <div className="routing-trace-grid">
                  <div className="routing-trace-item">
                    <span>{messages.traffic.northboundTransport}</span>
                    <strong>{request.northbound_transport}</strong>
                  </div>
                  <div className="routing-trace-item">
                    <span>{messages.traffic.southboundTransport}</span>
                    <strong>{request.southbound_transport ?? messages.traffic.pendingTransport}</strong>
                  </div>
                  <div className="routing-trace-item">
                    <span>{messages.traffic.stickyProvider}</span>
                    <strong>{request.sticky_provider ?? messages.traffic.noStickyProvider}</strong>
                  </div>
                  <div className="routing-trace-item">
                    <span>{messages.traffic.fallbackReason}</span>
                    <strong>{request.fallback_reason ?? messages.traffic.noFallbackReason}</strong>
                  </div>
                  <div className="routing-trace-item">
                    <span>{messages.traffic.turnState}</span>
                    <strong>{request.turn_state_status ?? messages.traffic.noTurnState}</strong>
                  </div>
                  <div className="routing-trace-item">
                    <span>{messages.traffic.turnStateToken}</span>
                    <strong>
                      {request.turn_state_token_present
                        ? messages.traffic.present
                        : messages.traffic.absent}
                    </strong>
                  </div>
                </div>
              </div>

              <div className="expanded-columns">
                <div className="expanded-block">
                  <span className="surface-label">{messages.traffic.fallbackAttempts}</span>
                  {request.attempts.length === 0 ? (
                    <p>{messages.traffic.noRetryAttempts}</p>
                  ) : (
                    <div className="attempt-list">
                      {request.attempts.map((attempt, attemptIndex) => (
                        <div
                          key={`${request.id}-${attempt.provider}-${attempt.url}-${attemptIndex}`}
                          className="attempt-item"
                        >
                          <div>
                            <strong>{attempt.provider}</strong>
                            <span>{messages.traffic.providerAttempt(attempt.provider_attempt)}</span>
                            <span>{attempt.url}</span>
                          </div>
                          <div>
                            <strong>{attempt.outcome}</strong>
                            <span>{attempt.status_code ?? messages.traffic.noStatus}</span>
                            <span>{describeNextAction(attempt.next_action)}</span>
                            <span>{messages.traffic.attemptTransport(attempt.transport)}</span>
                            <span>{attempt.sticky ? messages.traffic.stickyAttempt : messages.traffic.nonStickyAttempt}</span>
                            {attempt.fallback_reason ? (
                              <span>{messages.traffic.attemptFallbackReason(attempt.fallback_reason)}</span>
                            ) : null}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="expanded-block">
                  <span className="surface-label">{messages.traffic.error}</span>
                  <p>{request.error ?? messages.traffic.noErrorRecorded}</p>
                </div>
              </div>
            </div>
          </td>
        </motion.tr>
      ) : null}
    </Fragment>
  )
})

export function TrafficView({ requests, preset }: TrafficViewProps) {
  const { locale, messages } = useI18n()
  const [search, setSearch] = useState('')
  const [stateFilter, setStateFilter] = useState<RequestStateFilter>('all')
  const [kindFilter, setKindFilter] = useState<RequestKindFilter>('all')
  const [debugFilter, setDebugFilter] = useState<TrafficDebugFilter>('all')
  const [rowLimit, setRowLimit] = useState<RowLimit>(() => readStoredRowLimit())
  const [expandedRequestId, setExpandedRequestId] = useState<string | null>(null)
  const [copyState, setCopyState] = useState<CopyState>(null)
  const deferredSearch = useDeferredValue(search)

  useEffect(() => {
    if (typeof window === 'undefined') {
      return
    }

    try {
      window.localStorage.setItem(ROW_LIMIT_STORAGE_KEY, String(rowLimit))
    } catch {
      return
    }
  }, [rowLimit])

  useEffect(() => {
    if (preset === null) {
      return
    }
    const timeoutId = window.setTimeout(() => {
      setSearch(preset.search ?? '')
      setStateFilter((preset.state ?? 'all') as RequestStateFilter)
      setKindFilter(preset.kind ?? 'all')
      setDebugFilter('all')
      setExpandedRequestId(preset.requestId ?? null)
    }, 0)
    return () => window.clearTimeout(timeoutId)
  }, [preset])

  const filteredRequests = useMemo(() => {
    return requests.filter((request) => {
      const query = deferredSearch.trim().toLowerCase()
      const haystack = [
        request.model,
        request.final_provider ?? '',
        request.final_url ?? request.endpoint,
        request.error ?? '',
        request.status_code ?? '',
        request.sticky_provider ?? '',
        request.fallback_reason ?? '',
        request.turn_state_status ?? '',
        ...request.attempts.flatMap((attempt) => [
          attempt.provider,
          attempt.url,
          attempt.outcome,
          attempt.status_code ?? '',
          attempt.fallback_reason ?? '',
        ]),
      ].join(' ').toLowerCase()
      const matchesSearch = haystack.includes(query)
      const matchesState = stateFilter === 'all' ? true : request.state === stateFilter
      const matchesKind = kindFilter === 'all' ? true : request.request_kind === kindFilter
      const matchesDebug =
        debugFilter === 'all' ||
        (debugFilter === 'has_error' && requestHasError(request)) ||
        (debugFilter === 'failover' && requestHasFailover(request)) ||
        (debugFilter === 'retry' && requestHasRetry(request)) ||
        (debugFilter === 'sticky' && requestHasStickyOrTurnState(request))
      return matchesSearch && matchesState && matchesKind && matchesDebug
    })
  }, [requests, deferredSearch, stateFilter, kindFilter, debugFilter])

  const visibleRequests = useMemo(() => {
    return filteredRequests.slice(0, rowLimit)
  }, [filteredRequests, rowLimit])
  const filtersActive =
    search.trim() !== '' ||
    stateFilter !== 'all' ||
    kindFilter !== 'all' ||
    debugFilter !== 'all'

  function clearFilters() {
    setSearch('')
    setStateFilter('all')
    setKindFilter('all')
    setDebugFilter('all')
  }

  async function copyRequestDebugSummary(request: RecentRequest) {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error('Clipboard is unavailable')
      }
      await navigator.clipboard.writeText(buildRequestDebugSummary(request))
      setCopyState({ requestId: request.id, state: 'copied' })
    } catch {
      setCopyState({ requestId: request.id, state: 'failed' })
    }

    window.setTimeout(() => {
      setCopyState((current) => (current?.requestId === request.id ? null : current))
    }, 1800)
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
            <span className="eyebrow">{messages.traffic.eyebrow}</span>
            <h2>{messages.traffic.title}</h2>
          </div>
          <span className="section-caption">{messages.traffic.memoryOnly}</span>
        </div>

        <div className="toolbar-row">
          <label className="search-field">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={messages.traffic.searchPlaceholder}
            />
          </label>

          <DropdownSelect
            value={kindFilter}
            onChange={(val) => setKindFilter(val as RequestKindFilter)}
            options={[
              { value: 'all', label: messages.traffic.allKinds },
              { value: 'chat', label: messages.traffic.chat },
              { value: 'response', label: messages.traffic.response },
            ]}
          />

          <DropdownSelect
            value={stateFilter}
            onChange={(val) => setStateFilter(val as RequestStateFilter)}
            options={[
              { value: 'all', label: messages.traffic.allStates },
              { value: 'pending', label: messages.traffic.pending },
              { value: 'success', label: messages.traffic.success },
              { value: 'error', label: messages.traffic.failed },
              { value: 'interrupted', label: messages.traffic.interrupted },
              { value: 'stale', label: messages.traffic.stale },
            ]}
          />

          <DropdownSelect
            value={debugFilter}
            onChange={(val) => setDebugFilter(val as TrafficDebugFilter)}
            options={[
              { value: 'all', label: messages.traffic.allDebugFilters },
              { value: 'has_error', label: messages.traffic.hasError },
              { value: 'failover', label: messages.traffic.hasFailover },
              { value: 'retry', label: messages.traffic.hasRetry },
              { value: 'sticky', label: messages.traffic.hasSticky },
            ]}
          />

          <DropdownSelect
            value={rowLimit}
            onChange={setRowLimit}
            options={[
              { value: 10, label: messages.traffic.first10 },
              { value: 50, label: messages.traffic.first50 },
            ]}
            prefixLabel={messages.traffic.rowLimit}
            ariaLabel={messages.traffic.rowLimit}
          />

          {filtersActive ? (
            <button type="button" className="ghost-button" onClick={clearFilters}>
              <RotateCcw size={16} />
              {messages.traffic.clearFilters}
            </button>
          ) : null}
        </div>

        {filteredRequests.length === 0 ? (
          <div className="empty-state compact-empty">
            <h3>{messages.traffic.emptyTitle}</h3>
            <p>{messages.traffic.emptyCopy}</p>
          </div>
        ) : (
          <div className="table-shell">
            <table className="data-table traffic-table">
              <thead>
                <tr>
                  <th />
                  <th>{messages.traffic.request}</th>
                  <th>{messages.traffic.finalProvider}</th>
                  <th>{messages.traffic.status}</th>
                  <th>{messages.traffic.latency}</th>
                  <th>{messages.traffic.firstByte}</th>
                  <th>{messages.traffic.created}</th>
                </tr>
              </thead>
              <motion.tbody layout>
                <AnimatePresence mode="popLayout">
                  {visibleRequests.map((request) => (
                    <TrafficRow
                      key={request.id}
                      request={request}
                      expanded={expandedRequestId === request.id}
                      copyState={copyState}
                      locale={locale}
                      messages={messages}
                      onToggleExpand={() => setExpandedRequestId(expandedRequestId === request.id ? null : request.id)}
                      onCopyDebug={(req) => { void copyRequestDebugSummary(req) }}
                    />
                  ))}
                </AnimatePresence>
              </motion.tbody>
            </table>
          </div>
        )}
      </motion.section>
    </motion.div>
  )
}
