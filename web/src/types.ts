export type RequestAttempt = {
  provider: string
  url: string
  outcome: string
  retryable: boolean
  status_code: number | null
  provider_attempt: number
  next_action: 'retry_same_provider' | 'failover_next_provider' | 'return_to_client'
}

export type UsageSummary = {
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
}

export type RecentRequest = {
  id: string
  created_at: string
  endpoint: string
  request_kind: string
  model: string
  stream: boolean
  final_provider: string | null
  final_url: string | null
  status_code: number | null
  duration_ms: number | null
  ttfb_ms: number | null
  state: RequestState
  error: string | null
  usage: UsageSummary | null
  attempts: RequestAttempt[]
}

export type RequestState = 'pending' | 'success' | 'interrupted' | 'error'

export type HealthcheckSummary = {
  checked_at: string | null
  ok: boolean | null
  status_code: number | null
  latency_ms: number | null
  stream: boolean | null
  model: string | null
  error: string | null
}

export type HealthcheckConfigSummary = {
  stream: boolean
}

export type ProviderSummary = {
  name: string
  base_url: string
  enabled: boolean
  priority: number
  timeout_seconds: number
  max_failures: number
  cooldown_seconds: number
  models: string[]
  supports_all_models: boolean
  healthcheck_model: string | null
  consecutive_failures: number
  cooldown_until: string | null
  last_error: string | null
  last_failure_at: string | null
  last_success_at: string | null
  has_api_key: boolean
  healthcheck: HealthcheckSummary
}

export type ProviderStats = {
  provider_name: string
  served_requests: number
  successful_requests: number
  success_rate: number | null
  average_duration_ms: number | null
  average_ttfb_ms: number | null
  input_tokens: number
  output_tokens: number
  total_tokens: number
  requests_with_usage: number
}

export type DashboardResponse = {
  config_path: string
  listen_host: string
  listen_port: number
  primary_provider: string | null
  reloaded_at: string
  retry_policy: RetryPolicySummary
  healthcheck: HealthcheckConfigSummary
  providers: ProviderSummary[]
  recent_requests: RecentRequest[]
  stats: {
    global: ProviderStats
    providers: ProviderStats[]
  }
}

export type RetryPolicySummary = {
  retryable_status_codes: number[]
  same_provider_retry_count: number
  retry_interval_ms: number
}

export type MetricsWindow = '24h' | '7d'

export type MetricsPoint = {
  bucket_start: string
  value: number | null
}

export type ProviderBreakdown = {
  provider_name: string
  requests: number
  total_tokens: number
}

export type StateBreakdown = {
  state: 'success' | 'interrupted' | 'error'
  count: number
}

export type MetricsResponse = {
  window: MetricsWindow
  metrics_path: string
  last_flushed_at: string | null
  summary: {
    requests: number
    total_tokens: number
    average_duration_ms: number | null
    success_rate: number | null
  }
  timeseries: {
    requests: MetricsPoint[]
    tokens: MetricsPoint[]
    duration_ms: MetricsPoint[]
    success_rate: MetricsPoint[]
    average_ttfb_ms: MetricsPoint[]
  }
  breakdowns: {
    providers: ProviderBreakdown[]
    states: StateBreakdown[]
  }
}

export type MutationResponse = {
  message: string
  dashboard: DashboardResponse
}

export type ProviderFormState = {
  name: string
  baseUrl: string
  apiKey: string
  enabled: boolean
  priority: string
  modelMode: 'all' | 'explicit'
  modelText: string
  healthcheckModel: string
  timeoutSeconds: string
  maxFailures: string
  cooldownSeconds: string
}

export type RetryPolicyFormState = {
  retryableStatusCodes: string
  sameProviderRetryCount: string
  retryIntervalMs: string
}

export type HealthcheckSettingsFormState = {
  stream: boolean
}
