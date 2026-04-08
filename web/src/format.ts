import type {
  DashboardResponse,
  HealthcheckSummary,
  ProviderStats,
  ProviderSummary,
  RecentRequest,
} from './types'
import type { AppMessages } from './i18n'


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


export function requestHeadline(request: RecentRequest, messages: AppMessages): string {
  return `${request.request_kind === 'chat' ? messages.traffic.chat : messages.traffic.response} · ${request.model}`
}


export function getProviderStatus(
  provider: ProviderSummary,
  messages: AppMessages,
): { key: 'disabled' | 'cooling' | 'unsteady' | 'ready'; label: string; tone: string } {
  if (!provider.enabled) {
    return { key: 'disabled', label: messages.providerStatus.disabled, tone: 'slate' }
  }

  if (provider.cooldown_until && new Date(provider.cooldown_until).getTime() > Date.now()) {
    return { key: 'cooling', label: messages.providerStatus.cooling, tone: 'amber' }
  }

  if (provider.consecutive_failures > 0) {
    return { key: 'unsteady', label: messages.providerStatus.unsteady, tone: 'rose' }
  }

  return { key: 'ready', label: messages.providerStatus.ready, tone: 'emerald' }
}


export function getHealthState(
  healthcheck: HealthcheckSummary,
  messages: AppMessages,
): { key: 'not_checked' | 'healthy' | 'failed'; label: string; tone: string } {
  if (healthcheck.ok == null) {
    return { key: 'not_checked', label: messages.healthStatus.notChecked, tone: 'slate' }
  }

  if (healthcheck.ok) {
    return { key: 'healthy', label: messages.healthStatus.healthy, tone: 'emerald' }
  }

  return { key: 'failed', label: messages.healthStatus.failed, tone: 'rose' }
}


export function getModelsLabel(provider: ProviderSummary, messages: AppMessages): string {
  return provider.supports_all_models ? messages.providers.allModels : provider.models.join(', ')
}


export function getRequestStateLabel(state: RecentRequest['state'], messages: AppMessages): string {
  if (state === 'success') {
    return messages.requestState.success
  }
  if (state === 'interrupted') {
    return messages.requestState.interrupted
  }
  return messages.requestState.failed
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
