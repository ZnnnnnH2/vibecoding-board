export type RequestAttempt = {
  provider: string
  url: string
  outcome: string
  retryable: boolean
  status_code: number | null
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
  state: string
  error: string | null
  usage: UsageSummary | null
  attempts: RequestAttempt[]
}

export type HealthcheckSummary = {
  checked_at: string | null
  ok: boolean | null
  status_code: number | null
  latency_ms: number | null
  model: string | null
  error: string | null
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
  providers: ProviderSummary[]
  recent_requests: RecentRequest[]
  stats: {
    global: ProviderStats
    providers: ProviderStats[]
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
