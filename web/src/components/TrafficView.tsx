import { Fragment, useDeferredValue, useState } from 'react'
import { ChevronDown, ChevronUp, Search } from 'lucide-react'

import {
  formatTimestamp,
  requestHeadline,
} from '../format'

import type { RecentRequest } from '../types'


type RequestStateFilter = 'all' | 'success' | 'failed' | 'interrupted'
type RequestKindFilter = 'all' | 'chat' | 'response'

type TrafficViewProps = {
  requests: RecentRequest[]
}


export function TrafficView({ requests }: TrafficViewProps) {
  const [search, setSearch] = useState('')
  const [stateFilter, setStateFilter] = useState<RequestStateFilter>('all')
  const [kindFilter, setKindFilter] = useState<RequestKindFilter>('all')
  const [expandedRequestId, setExpandedRequestId] = useState<string | null>(null)
  const deferredSearch = useDeferredValue(search)

  const visibleRequests = requests.filter((request) => {
    const query = deferredSearch.trim().toLowerCase()
    const haystack = `${request.model} ${request.final_provider ?? ''} ${request.final_url ?? request.endpoint}`.toLowerCase()
    const matchesSearch = haystack.includes(query)
    const matchesState = stateFilter === 'all' ? true : request.state === stateFilter
    const matchesKind = kindFilter === 'all' ? true : request.request_kind === kindFilter
    return matchesSearch && matchesState && matchesKind
  })

  return (
    <div className="page-stack">
      <section className="surface-card">
        <div className="section-header">
          <div>
            <span className="eyebrow">Traffic</span>
            <h2>Recent request log</h2>
          </div>
          <span className="section-caption">Memory only. Cleared on process restart.</span>
        </div>

        <div className="toolbar-row">
          <label className="search-field">
            <Search size={16} />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search by model, provider, or URL"
            />
          </label>

          <label className="select-field">
            <select
              value={kindFilter}
              onChange={(event) => setKindFilter(event.target.value as RequestKindFilter)}
            >
              <option value="all">All kinds</option>
              <option value="chat">Chat</option>
              <option value="response">Response</option>
            </select>
          </label>

          <label className="select-field">
            <select
              value={stateFilter}
              onChange={(event) => setStateFilter(event.target.value as RequestStateFilter)}
            >
              <option value="all">All states</option>
              <option value="success">Success</option>
              <option value="failed">Failed</option>
              <option value="interrupted">Interrupted</option>
            </select>
          </label>
        </div>

        {visibleRequests.length === 0 ? (
          <div className="empty-state compact-empty">
            <h3>No traffic rows match the current filters</h3>
            <p>As requests pass through `/v1`, routing records will appear here.</p>
          </div>
        ) : (
          <div className="table-shell">
            <table className="data-table traffic-table">
              <thead>
                <tr>
                  <th />
                  <th>Request</th>
                  <th>Final provider</th>
                  <th>Status</th>
                  <th>Latency</th>
                  <th>First byte</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {visibleRequests.map((request) => {
                  const expanded = expandedRequestId === request.id
                  return (
                    <Fragment key={request.id}>
                      <tr key={request.id}>
                        <td>
                          <button
                            type="button"
                            className="expand-button"
                            onClick={() => setExpandedRequestId(expanded ? null : request.id)}
                            aria-label={expanded ? 'Collapse request details' : 'Expand request details'}
                          >
                            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                          </button>
                        </td>
                        <td>
                          <div className="table-primary">
                            <strong>{requestHeadline(request)}</strong>
                            <span>{request.final_url ?? request.endpoint}</span>
                          </div>
                        </td>
                        <td>{request.final_provider ?? 'No provider selected'}</td>
                        <td>
                          <span className={`pill pill-${request.state === 'success' ? 'emerald' : request.state === 'interrupted' ? 'amber' : 'rose'}`}>
                            {request.state}
                          </span>
                        </td>
                        <td>{request.duration_ms ?? 'N/A'} ms</td>
                        <td>{request.ttfb_ms ?? 'N/A'} ms</td>
                        <td>{formatTimestamp(request.created_at)}</td>
                      </tr>
                      {expanded ? (
                        <tr className="expanded-row">
                          <td colSpan={7}>
                            <div className="expanded-panel">
                              <div className="expanded-grid">
                                <div className="expanded-card">
                                  <span className="surface-label">Endpoint</span>
                                  <strong>{request.endpoint}</strong>
                                </div>
                                <div className="expanded-card">
                                  <span className="surface-label">Mode</span>
                                  <strong>{request.stream ? 'Streaming' : 'Standard'}</strong>
                                </div>
                                <div className="expanded-card">
                                  <span className="surface-label">HTTP status</span>
                                  <strong>{request.status_code ?? 'N/A'}</strong>
                                </div>
                                <div className="expanded-card">
                                  <span className="surface-label">Usage</span>
                                  <strong>
                                    {request.usage
                                      ? `${request.usage.input_tokens ?? 'N/A'} / ${request.usage.output_tokens ?? 'N/A'} / ${request.usage.total_tokens ?? 'N/A'}`
                                      : 'No usage fields'}
                                  </strong>
                                </div>
                              </div>

                              <div className="expanded-columns">
                                <div className="expanded-block">
                                  <span className="surface-label">Fallback attempts</span>
                                  {request.attempts.length === 0 ? (
                                    <p>No retry attempts were required before the final route was established.</p>
                                  ) : (
                                    <div className="attempt-list">
                                      {request.attempts.map((attempt) => (
                                        <div
                                          key={`${request.id}-${attempt.provider}-${attempt.url}`}
                                          className="attempt-item"
                                        >
                                          <div>
                                            <strong>{attempt.provider}</strong>
                                            <span>{attempt.url}</span>
                                          </div>
                                          <div>
                                            <strong>{attempt.outcome}</strong>
                                            <span>{attempt.status_code ?? 'no status'}</span>
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>

                                <div className="expanded-block">
                                  <span className="surface-label">Error</span>
                                  <p>{request.error ?? 'No error recorded for this request.'}</p>
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
