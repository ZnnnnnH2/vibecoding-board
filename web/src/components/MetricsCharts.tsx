import {
  Activity,
  BarChart3,
  CircleDashed,
  Clock3,
  Coins,
  TrendingUp,
} from 'lucide-react'

import { formatCountCompact, formatTimestamp } from '../format'
import { useI18n } from '../i18n'

import type {
  MetricsPoint,
  ProviderBreakdown,
  StateBreakdown,
} from '../types'


type LineTrendCardProps = {
  title: string
  description: string
  points: MetricsPoint[]
  latestLabel: string
  formatLatestValue?: (value: number | null | undefined) => string
  color: string
  icon: 'requests' | 'tokens' | 'duration'
}

type DualTrendCardProps = {
  title: string
  description: string
  primaryPoints: MetricsPoint[]
  primaryLabel: string
  primaryColor: string
  secondaryPoints: MetricsPoint[]
  secondaryLabel: string
  secondaryColor: string
}

type DistributionBarCardProps = {
  title: string
  description: string
  items: ProviderBreakdown[]
}

type DonutCardProps = {
  title: string
  description: string
  items: Array<StateBreakdown & { label: string; color: string }>
}


function iconForTrend(kind: LineTrendCardProps['icon']) {
  if (kind === 'tokens') {
    return <Coins size={18} />
  }
  if (kind === 'duration') {
    return <Clock3 size={18} />
  }
  return <TrendingUp size={18} />
}


function normalizePoints(points: MetricsPoint[]) {
  if (points.length === 0) {
    return { path: '', areaPath: '', max: 0, min: 0 }
  }

  const values = points.map((point) => point.value ?? 0)
  const min = Math.min(...values)
  const max = Math.max(...values, min + 1)
  const range = max - min || 1
  const width = 100
  const height = 54

  const coordinates = values.map((value, index) => {
    const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width
    const y = height - (((value - min) / range) * height)
    return { x, y }
  })

  const path = coordinates.map((coord, index) => `${index === 0 ? 'M' : 'L'} ${coord.x} ${coord.y}`).join(' ')
  const areaPath = `${path} L ${coordinates[coordinates.length - 1].x} ${height} L ${coordinates[0].x} ${height} Z`

  return { path, areaPath, max, min }
}


function latestPoint(points: MetricsPoint[]): MetricsPoint | null {
  for (let index = points.length - 1; index >= 0; index -= 1) {
    if (points[index].value != null) {
      return points[index]
    }
  }
  return null
}


function axisLabels(points: MetricsPoint[], locale: string) {
  if (points.length === 0) {
    return []
  }

  const indexes = Array.from(new Set([0, Math.floor((points.length - 1) / 2), points.length - 1]))
  return indexes.map((index) => ({
    key: `${points[index].bucket_start}:${index}`,
    label: formatTimestamp(points[index].bucket_start, locale),
  }))
}


export function LineTrendCard({
  title,
  description,
  points,
  latestLabel,
  formatLatestValue,
  color,
  icon,
}: LineTrendCardProps) {
  const { locale } = useI18n()
  const { path, areaPath } = normalizePoints(points)
  const latest = latestPoint(points)

  return (
    <article className="chart-card">
      <div className="chart-card-head">
        <div>
          <span className="surface-label">{title}</span>
          <h3>
            {latest == null || latest.value == null
              ? latestLabel
              : `${latestLabel} · ${formatLatestValue ? formatLatestValue(latest.value) : latest.value}`}
          </h3>
        </div>
        <div className="chart-card-icon" style={{ color }}>
          {iconForTrend(icon)}
        </div>
      </div>

      <p className="chart-card-copy">{description}</p>

      <div className="chart-frame">
        {path ? (
          <svg viewBox="0 0 100 60" className="trend-svg" preserveAspectRatio="none" aria-hidden="true">
            <path d={areaPath} fill={color} opacity="0.12" />
            <path d={path} fill="none" stroke={color} strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        ) : null}
      </div>

      <div className="chart-axis-labels">
        {axisLabels(points, locale).map((item) => (
          <span key={item.key}>{item.label}</span>
        ))}
      </div>
    </article>
  )
}


export function DualTrendCard({
  title,
  description,
  primaryPoints,
  primaryLabel,
  primaryColor,
  secondaryPoints,
  secondaryLabel,
  secondaryColor,
}: DualTrendCardProps) {
  const { locale } = useI18n()
  const primary = normalizePoints(primaryPoints)
  const secondary = normalizePoints(secondaryPoints)

  return (
    <article className="chart-card">
      <div className="chart-card-head">
        <div>
          <span className="surface-label">{title}</span>
          <h3>{description}</h3>
        </div>
        <div className="chart-card-icon chart-card-icon-neutral">
          <Activity size={18} />
        </div>
      </div>

      <div className="dual-legend">
        <div>
          <span className="legend-swatch" style={{ background: primaryColor }} />
          <strong>{primaryLabel}</strong>
        </div>
        <div>
          <span className="legend-swatch" style={{ background: secondaryColor }} />
          <strong>{secondaryLabel}</strong>
        </div>
      </div>

      <div className="chart-frame">
        <svg viewBox="0 0 100 60" className="trend-svg" preserveAspectRatio="none" aria-hidden="true">
          {primary.path ? <path d={primary.path} fill="none" stroke={primaryColor} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" /> : null}
          {secondary.path ? <path d={secondary.path} fill="none" stroke={secondaryColor} strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" strokeDasharray="6 4" /> : null}
        </svg>
      </div>

      <div className="chart-axis-labels">
        {axisLabels(primaryPoints, locale).map((item) => (
          <span key={item.key}>{item.label}</span>
        ))}
      </div>
    </article>
  )
}


export function DistributionBarCard({
  title,
  description,
  items,
}: DistributionBarCardProps) {
  const { messages } = useI18n()
  const total = items.reduce((sum, item) => sum + item.requests, 0)
  const visibleItems = items.slice(0, 6)

  return (
    <article className="chart-card">
      <div className="chart-card-head">
        <div>
          <span className="surface-label">{title}</span>
          <h3>{formatCountCompact(total)}</h3>
        </div>
        <div className="chart-card-icon chart-card-icon-neutral">
          <BarChart3 size={18} />
        </div>
      </div>

      <p className="chart-card-copy">{description}</p>

      {visibleItems.length === 0 ? (
        <div className="empty-inline">
          <span>{messages.overview.noDistributionData}</span>
        </div>
      ) : (
        <div className="bar-list">
          {visibleItems.map((item) => {
            const width = total === 0 ? 0 : (item.requests / total) * 100
            return (
              <div key={item.provider_name} className="bar-list-item">
                <div className="bar-list-head">
                  <strong>{item.provider_name}</strong>
                  <span>{formatCountCompact(item.requests)} req · {formatCountCompact(item.total_tokens)} tok</span>
                </div>
                <div className="bar-track">
                  <div className="bar-fill" style={{ width: `${width}%` }} />
                </div>
              </div>
            )
          })}
        </div>
      )}
    </article>
  )
}


export function DonutCard({
  title,
  description,
  items,
}: DonutCardProps) {
  const { messages } = useI18n()
  const total = items.reduce((sum, item) => sum + item.count, 0)
  const circumference = 2 * Math.PI * 34
  const segments = items.map((item, index) => {
    const offset = items
      .slice(0, index)
      .reduce((sum, previous) => sum + (total === 0 ? 0 : (previous.count / total) * circumference), 0)
    const segmentLength = total === 0 ? 0 : (item.count / total) * circumference
    return {
      item,
      offset,
      segmentLength,
    }
  })

  return (
    <article className="chart-card">
      <div className="chart-card-head">
        <div>
          <span className="surface-label">{title}</span>
          <h3>{formatCountCompact(total)}</h3>
        </div>
        <div className="chart-card-icon chart-card-icon-neutral">
          <CircleDashed size={18} />
        </div>
      </div>

      <p className="chart-card-copy">{description}</p>

      <div className="donut-layout">
        <svg viewBox="0 0 100 100" className="donut-svg" aria-hidden="true">
          <circle cx="50" cy="50" r="34" fill="none" stroke="rgba(148, 163, 184, 0.16)" strokeWidth="12" />
          {segments.map(({ item, offset, segmentLength }) => (
              <circle
                key={item.state}
                cx="50"
                cy="50"
                r="34"
                fill="none"
                stroke={item.color}
                strokeWidth="12"
                strokeDasharray={`${segmentLength} ${circumference - segmentLength}`}
                strokeDashoffset={-offset}
                strokeLinecap="butt"
                transform="rotate(-90 50 50)"
              />
          ))}
          <text x="50" y="47" textAnchor="middle" className="donut-total-label">
            {formatCountCompact(total)}
          </text>
          <text x="50" y="59" textAnchor="middle" className="donut-total-caption">
            {messages.overview.totalLabel}
          </text>
        </svg>

        <div className="donut-legend">
          {items.map((item) => (
            <div key={item.state} className="donut-legend-item">
              <span className="legend-swatch" style={{ background: item.color }} />
              <div>
                <strong>{item.label}</strong>
                <span>{formatCountCompact(item.count)}</span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </article>
  )
}
