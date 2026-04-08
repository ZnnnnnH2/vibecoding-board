import type {
  DashboardResponse,
  HealthcheckSummary,
  ProviderStats,
  ProviderSummary,
  RecentRequest,
  RequestState,
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

  if (isProviderCooling(provider)) {
    return { key: 'cooling', label: messages.providerStatus.cooling, tone: 'amber' }
  }

  if (provider.consecutive_failures > 0) {
    return { key: 'unsteady', label: messages.providerStatus.unsteady, tone: 'rose' }
  }

  return { key: 'ready', label: messages.providerStatus.ready, tone: 'emerald' }
}


export function isProviderCooling(provider: Pick<ProviderSummary, 'cooldown_until'>): boolean {
  return provider.cooldown_until != null && new Date(provider.cooldown_until).getTime() > Date.now()
}


export function getProviderRoutingHint(provider: ProviderSummary, messages: AppMessages): string {
  if (!provider.enabled) {
    return messages.providers.ignoredByRouter
  }

  if (isProviderCooling(provider)) {
    return messages.providers.temporarilySkipped
  }

  return messages.providers.availableForMatchingModels
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
  return getRequestStateMeta(state, messages).label
}


export function getRequestStateMeta(
  state: RequestState,
  messages: AppMessages,
): { label: string; tone: 'emerald' | 'amber' | 'rose' | 'slate' } {
  if (state === 'pending') {
    return { label: messages.requestState.pending, tone: 'slate' }
  }
  if (state === 'success') {
    return { label: messages.requestState.success, tone: 'emerald' }
  }
  if (state === 'interrupted') {
    return { label: messages.requestState.interrupted, tone: 'amber' }
  }
  return { label: messages.requestState.failed, tone: 'rose' }
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
