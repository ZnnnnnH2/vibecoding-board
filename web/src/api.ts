import type {
  DashboardResponse,
  MetricsResponse,
  MetricsWindow,
  MutationResponse,
  ProviderFormState,
  RetryPolicyFormState,
} from './types'
import type { AppLocale } from './i18n'


let currentLocale: AppLocale = 'en'


export function setApiLocale(locale: AppLocale): void {
  currentLocale = locale
}


function fallbackRequestError(status: number): string {
  if (currentLocale === 'zh-CN') {
    return `请求失败，状态码 ${status}`
  }
  return `Request failed with status ${status}`
}


function localMessage(enText: string, zhText: string): string {
  return currentLocale === 'zh-CN' ? zhText : enText
}


function parseError(payload: unknown, fallback: string): string {
  if (typeof payload !== 'object' || payload === null) {
    return fallback
  }

  const detail = 'detail' in payload ? payload.detail : undefined
  if (typeof detail === 'string' && detail) {
    return detail
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item !== 'object' || item === null) {
          return null
        }
        const msg = 'msg' in item && typeof item.msg === 'string' ? item.msg : null
        if (!msg) {
          return null
        }
        const location =
          'loc' in item && Array.isArray(item.loc)
            ? item.loc
                .filter(
                  (part: unknown): part is string | number => typeof part === 'string' || typeof part === 'number',
                )
                .filter((part: string | number) => part !== 'body')
                .join('.')
            : ''
        return location ? `${location}: ${msg}` : msg
      })
      .filter((message): message is string => Boolean(message))
    if (messages.length > 0) {
      return messages.join('; ')
    }
  }

  const error = 'error' in payload ? payload.error : undefined
  if (typeof error === 'object' && error !== null && 'message' in error && typeof error.message === 'string') {
    return error.message
  }

  return fallback
}


async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      'Content-Type': 'application/json',
      'X-Admin-Locale': currentLocale,
      ...(init?.headers ?? {}),
    },
    ...init,
  })

  if (!response.ok) {
    let payload: unknown = null
    try {
      payload = await response.json()
    } catch {
      payload = null
    }
    throw new Error(parseError(payload, fallbackRequestError(response.status)))
  }

  return (await response.json()) as T
}


function buildProviderPayload(form: ProviderFormState) {
  const models =
    form.modelMode === 'all'
      ? ['*']
      : form.modelText
          .split('\n')
          .map((value) => value.trim())
          .filter(Boolean)
  const priority = Number.parseInt(form.priority, 10)

  return {
    name: form.name.trim(),
    base_url: form.baseUrl.trim(),
    api_key: form.apiKey.trim(),
    enabled: form.enabled,
    priority: Number.isNaN(priority) ? 10 : priority,
    models,
    healthcheck_model: form.healthcheckModel.trim() || null,
    timeout_seconds: Number(form.timeoutSeconds),
    max_failures: Number(form.maxFailures),
    cooldown_seconds: Number(form.cooldownSeconds),
  }
}


function buildRetryPolicyPayload(form: RetryPolicyFormState) {
  const rawTokens = form.retryableStatusCodes
    .split(/[\s,]+/)
    .map((value) => value.trim())
    .filter(Boolean)

  const invalidToken = rawTokens.find((token) => !/^\d+$/.test(token))
  if (invalidToken) {
    throw new Error(localMessage(`Invalid status code: ${invalidToken}`, `无效状态码：${invalidToken}`))
  }

  const retryableStatusCodes = rawTokens.map((token) => Number.parseInt(token, 10))
  const sameProviderRetryCount = Number.parseInt(form.sameProviderRetryCount, 10)
  const retryIntervalMs = Number.parseInt(form.retryIntervalMs, 10)

  if (!Number.isFinite(sameProviderRetryCount) || sameProviderRetryCount < 0) {
    throw new Error(localMessage('Retry count must be a non-negative integer.', '重试次数必须是非负整数。'))
  }
  if (!Number.isFinite(retryIntervalMs) || retryIntervalMs < 0) {
    throw new Error(localMessage('Retry interval must be a non-negative integer.', '重试间隔必须是非负整数。'))
  }

  return {
    retryable_status_codes: retryableStatusCodes,
    same_provider_retry_count: sameProviderRetryCount,
    retry_interval_ms: retryIntervalMs,
  }
}


export const api = {
  dashboard(signal?: AbortSignal): Promise<DashboardResponse> {
    return request<DashboardResponse>('/admin/api/dashboard', { signal })
  },

  metrics(window: MetricsWindow, signal?: AbortSignal): Promise<MetricsResponse> {
    return request<MetricsResponse>(`/admin/api/metrics?window=${window}`, { signal })
  },

  createProvider(form: ProviderFormState): Promise<MutationResponse> {
    return request<MutationResponse>('/admin/api/providers', {
      method: 'POST',
      body: JSON.stringify(buildProviderPayload(form)),
    })
  },

  updateProvider(name: string, form: ProviderFormState): Promise<MutationResponse> {
    return request<MutationResponse>(`/admin/api/providers/${encodeURIComponent(name)}`, {
      method: 'PUT',
      body: JSON.stringify(buildProviderPayload(form)),
    })
  },

  updateProviderPriority(name: string, priority: number): Promise<MutationResponse> {
    return request<MutationResponse>(`/admin/api/providers/${encodeURIComponent(name)}/priority`, {
      method: 'PATCH',
      body: JSON.stringify({ priority }),
    })
  },

  promoteProvider(name: string): Promise<MutationResponse> {
    return request<MutationResponse>(`/admin/api/providers/${encodeURIComponent(name)}/promote`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
  },

  toggleProvider(name: string): Promise<MutationResponse> {
    return request<MutationResponse>(`/admin/api/providers/${encodeURIComponent(name)}/toggle`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
  },

  healthcheckProvider(name: string): Promise<MutationResponse> {
    return request<MutationResponse>(`/admin/api/providers/${encodeURIComponent(name)}/healthcheck`, {
      method: 'POST',
      body: JSON.stringify({}),
    })
  },

  deleteProvider(name: string): Promise<MutationResponse> {
    return request<MutationResponse>(`/admin/api/providers/${encodeURIComponent(name)}`, {
      method: 'DELETE',
    })
  },

  updateRetryPolicy(form: RetryPolicyFormState): Promise<MutationResponse> {
    return request<MutationResponse>('/admin/api/retry-policy', {
      method: 'PATCH',
      body: JSON.stringify(buildRetryPolicyPayload(form)),
    })
  },
}
