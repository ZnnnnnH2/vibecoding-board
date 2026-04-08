import { Fragment, useDeferredValue, useState } from 'react'
import { ChevronDown, ChevronUp, Search } from 'lucide-react'

import {
  formatTimestamp,
  getRequestStateMeta,
  requestHeadline,
} from '../format'
import { useI18n } from '../i18n'

import type { RecentRequest } from '../types'


type RequestStateFilter = 'all' | 'pending' | 'success' | 'error' | 'interrupted'
type RequestKindFilter = 'all' | 'chat' | 'response'

type TrafficViewProps = {
  requests: RecentRequest[]
}


export function TrafficView({ requests }: TrafficViewProps) {
  const { messages } = useI18n()
  const [search, setSearch] = useState('')
  const [stateFilter, setStateFilter] = useState<RequestStateFilter>('all')
  const [kindFilter, setKindFilter] = useState<RequestKindFilter>('all')
  const [rowLimit, setRowLimit] = useState<10 | 50>(10)
  const [expandedRequestId, setExpandedRequestId] = useState<string | null>(null)
  const deferredSearch = useDeferredValue(search)

  const filteredRequests = requests.filter((request) => {
    const query = deferredSearch.trim().toLowerCase()
    const haystack = `${request.model} ${request.final_provider ?? ''} ${request.final_url ?? request.endpoint}`.toLowerCase()
    const matchesSearch = haystack.includes(query)
    const matchesState = stateFilter === 'all' ? true : request.state === stateFilter
    const matchesKind = kindFilter === 'all' ? true : request.request_kind === kindFilter
    return matchesSearch && matchesState && matchesKind
  })
  const visibleRequests = filteredRequests.slice(0, rowLimit)

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
    <div className="page-stack">
      <section className="surface-card">
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

          <label className="select-field">
            <select
              value={kindFilter}
              onChange={(event) => setKindFilter(event.target.value as RequestKindFilter)}
            >
              <option value="all">{messages.traffic.allKinds}</option>
              <option value="chat">{messages.traffic.chat}</option>
              <option value="response">{messages.traffic.response}</option>
            </select>
          </label>

          <label className="select-field">
            <select
              value={stateFilter}
              onChange={(event) => setStateFilter(event.target.value as RequestStateFilter)}
            >
              <option value="all">{messages.traffic.allStates}</option>
              <option value="pending">{messages.traffic.pending}</option>
              <option value="success">{messages.traffic.success}</option>
              <option value="error">{messages.traffic.failed}</option>
              <option value="interrupted">{messages.traffic.interrupted}</option>
            </select>
          </label>

          <label className="select-field">
            <span className="surface-label">{messages.traffic.rowLimit}</span>
            <select
              value={rowLimit}
              onChange={(event) => setRowLimit(Number(event.target.value) as 10 | 50)}
              aria-label={messages.traffic.rowLimit}
            >
              <option value={10}>{messages.traffic.first10}</option>
              <option value={50}>{messages.traffic.first50}</option>
            </select>
          </label>
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
              <tbody>
                {visibleRequests.map((request) => {
                  const expanded = expandedRequestId === request.id
                  const requestState = getRequestStateMeta(request.state, messages)
                  return (
                    <Fragment key={request.id}>
                      <tr key={request.id}>
                        <td>
                          <button
                            type="button"
                            className="expand-button"
                            onClick={() => setExpandedRequestId(expanded ? null : request.id)}
                            aria-label={expanded ? messages.traffic.collapseDetails : messages.traffic.expandDetails}
                          >
                            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                          </button>
                        </td>
                        <td>
                          <div className="table-primary">
                            <strong>{requestHeadline(request, messages)}</strong>
                            <span>{request.final_url ?? request.endpoint}</span>
                          </div>
                        </td>
                        <td>{request.final_provider ?? messages.traffic.noProviderSelected}</td>
                        <td>
                          <span className={`pill pill-${requestState.tone}`}>
                            {requestState.label}
                          </span>
                        </td>
                        <td>{request.duration_ms ?? messages.app.notAvailable} ms</td>
                        <td>{request.ttfb_ms ?? messages.app.notAvailable} ms</td>
                        <td>{formatTimestamp(request.created_at)}</td>
                      </tr>
                      {expanded ? (
                        <tr className="expanded-row">
                          <td colSpan={7}>
                            <div className="expanded-panel">
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
                                      ? `${request.usage.input_tokens ?? messages.app.notAvailable} / ${request.usage.output_tokens ?? messages.app.notAvailable} / ${request.usage.total_tokens ?? messages.app.notAvailable}`
                                      : messages.traffic.noUsageFields}
                                  </strong>
                                </div>
                              </div>

                              <div className="expanded-columns">
                                <div className="expanded-block">
                                  <span className="surface-label">{messages.traffic.fallbackAttempts}</span>
                                  {request.attempts.length === 0 ? (
                                    <p>{messages.traffic.noRetryAttempts}</p>
                                  ) : (
                                    <div className="attempt-list">
                                      {request.attempts.map((attempt) => (
                                        <div
                                          key={`${request.id}-${attempt.provider}-${attempt.url}`}
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
                        </tr>
                      ) : null}
                    </Fragment>
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
