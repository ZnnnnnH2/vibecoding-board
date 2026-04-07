import type {
  DashboardResponse,
  HealthcheckSummary,
  ProviderStats,
  ProviderSummary,
  RecentRequest,
} from './types'


export function formatTimestamp(value: string | null): string {
  if (!value) {
    return 'N/A'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}


export function formatPercent(value: number | null): string {
  if (value == null) {
    return 'N/A'
  }
  return `${(value * 100).toFixed(1)}%`
}


export function formatNumber(value: number | null): string {
  if (value == null) {
    return 'N/A'
  }
  return `${Math.round(value)}`
}


export function requestHeadline(request: RecentRequest): string {
  return `${request.request_kind === 'chat' ? 'Chat' : 'Response'} · ${request.model}`
}


export function getProviderStatus(provider: ProviderSummary): { label: string; tone: string } {
  if (!provider.enabled) {
    return { label: 'Disabled', tone: 'slate' }
  }

  if (provider.cooldown_until && new Date(provider.cooldown_until).getTime() > Date.now()) {
    return { label: 'Cooling', tone: 'amber' }
  }

  if (provider.consecutive_failures > 0) {
    return { label: 'Unsteady', tone: 'rose' }
  }

  return { label: 'Ready', tone: 'emerald' }
}


export function getHealthState(healthcheck: HealthcheckSummary): { label: string; tone: string } {
  if (healthcheck.ok == null) {
    return { label: 'Not checked', tone: 'slate' }
  }

  if (healthcheck.ok) {
    return { label: 'Healthy', tone: 'emerald' }
  }

  return { label: 'Failed', tone: 'rose' }
}


export function getModelsLabel(provider: ProviderSummary): string {
  return provider.supports_all_models ? 'All models' : provider.models.join(', ')
}


export function sortProviders(providers: ProviderSummary[]): ProviderSummary[] {
  return [...providers].sort((left, right) => {
    if (left.priority !== right.priority) {
      return left.priority - right.priority
    }
    return left.name.localeCompare(right.name)
  })
}


export function findProviderStats(
  stats: DashboardResponse['stats'] | undefined,
  providerName: string,
): ProviderStats | undefined {
  return stats?.providers.find((entry) => entry.provider_name === providerName)
}
