# Retry Policy Settings Design

## Goal
Add configurable same-provider retry behavior for retryable upstream HTTP responses while preserving the current priority-based provider failover model.

The new behavior should:
- allow users to configure which status codes are retryable
- retry the same provider before failing over to the next provider
- expose retry policy controls in the admin UI
- keep streaming failover limited to the period before the first chunk is sent to the client

## Scope

In scope:
- top-level retry policy config
- runtime support for same-provider retries on configured status codes
- provider cooldown when same-provider retries are exhausted
- admin API support for reading and updating retry policy
- admin UI settings page for retry policy
- request-log visibility for same-provider retry attempts
- tests for config validation, non-stream flow, stream flow before first chunk, and admin mutation flow

Out of scope:
- mid-stream failover after the first chunk has been sent
- per-provider retry policy overrides
- persistent metrics for internal retry attempt counts
- changing the behavior of network exceptions beyond the current logic

## Recommended Approach
Add a new top-level `retry_policy` section to the config and runtime snapshot. Rework the forwarding logic so each provider attempt becomes a two-level process:

1. provider selection across candidates
2. same-provider retries within the selected provider

This keeps the existing routing order and cooldown model intact while making the retry behavior configurable and explicit.

## Configuration Model

Add a new config section:

```yaml
retry_policy:
  retryable_status_codes: [429, 500, 502, 503, 504]
  same_provider_retry_count: 0
  retry_interval_ms: 0
```

Fields:
- `retryable_status_codes`: list of HTTP status codes that trigger same-provider retry
- `same_provider_retry_count`: number of extra attempts after the initial response from the current provider
- `retry_interval_ms`: wait time between same-provider retries

Validation rules:
- each status code must be an integer in `400..599`
- status codes are normalized to a unique sorted list
- `same_provider_retry_count >= 0`
- `retry_interval_ms >= 0`

Compatibility:
- missing `retry_policy` uses the default values above
- existing configs remain valid

## Runtime Behavior

### Non-stream requests
For each candidate provider:

1. send the request
2. if the response is successful, return it immediately
3. if the response is non-retryable, return it immediately
4. if the response status code is retryable:
   - record an attempt entry
   - if same-provider retry budget remains, sleep for `retry_interval_ms` and retry the same provider
   - if retry budget is exhausted, mark the provider as failed and force it into cooldown, then move to the next provider

If all candidates are exhausted, return the existing aggregated local `503` error.

### Stream requests
Streaming keeps the existing commit boundary:

- same-provider retries and provider failover are allowed only before the first chunk is sent to the client
- after the first chunk is sent, the response is committed and no failover occurs
- if a stream later breaks, it remains an `interrupted` request

## Provider State and Cooldown
When a provider exhausts all same-provider retry attempts for a retryable status code, it is considered exhausted for that request and is placed into cooldown immediately.

This uses a dedicated runtime path instead of only incrementing the existing consecutive-failure counter once per internal retry attempt. The intent is:
- request logs show every internal attempt
- provider runtime state reflects that the provider was abandoned after exhausting the configured retry budget

## Request Logging
Extend request-attempt entries to make same-provider retries visible.

New attempt fields:
- `provider_attempt`: 1-based attempt number for the same provider
- `next_action`: one of `retry_same_provider`, `failover_next_provider`, `return_to_client`

This allows the traffic view to show:
- how many times the proxy retried a provider
- when the proxy gave up on that provider
- when failover to the next provider occurred

Metrics remain request-level only. Internal attempts are not counted as separate served requests.

## Admin API
Extend the dashboard payload with:

```json
{
  "retry_policy": {
    "retryable_status_codes": [429, 500, 502, 503, 504],
    "same_provider_retry_count": 0,
    "retry_interval_ms": 0
  }
}
```

Add:
- `PATCH /admin/api/retry-policy`

Payload:

```json
{
  "retryable_status_codes": [500, 502, 503, 504, 521, 522, 523, 524],
  "same_provider_retry_count": 1,
  "retry_interval_ms": 300
}
```

Response follows the existing mutation pattern:

```json
{
  "message": "...",
  "dashboard": { ... }
}
```

## Admin UI
Add a new `Settings` page to the admin shell navigation.

The page includes a `Retry Policy` section with:
- retryable status codes input
- same-provider retry count input
- retry interval input in milliseconds

The page also includes short behavioral notes:
- retries happen on the current provider before provider failover
- provider failover only happens after same-provider retries are exhausted
- exhausted providers enter cooldown
- stream retries only apply before the first chunk
- local clients wait until the proxy succeeds, fails over, or returns a final failure

## Testing Strategy

Backend tests:
- config validation and normalization for `retry_policy`
- non-stream request succeeds after same-provider retry
- non-stream request exhausts same-provider retries, then fails over
- stream request retries before first chunk and succeeds
- exhausted provider enters cooldown
- dashboard includes retry policy data
- retry-policy admin mutation updates runtime and config

Frontend verification:
- settings page reads dashboard retry policy
- settings mutation sends normalized payload
- `npm run lint`
- `npm run build`

## Files Expected to Change
- `vibecoding_board/config.py`
- `vibecoding_board/runtime.py`
- `vibecoding_board/registry.py`
- `vibecoding_board/request_log.py`
- `vibecoding_board/service.py`
- `vibecoding_board/admin_api.py`
- `config.example.yaml`
- `tests/`
- `web/src/App.tsx`
- `web/src/api.ts`
- `web/src/i18n.tsx`
- `web/src/types.ts`
- `web/src/components/`

## Approval State
This design reflects the user-approved direction on 2026-04-08:
- retryable status codes are user-configurable
- the proxy retries the same provider before failover
- retry count and interval are user-configurable
- exhausted providers enter cooldown
- retry policy is managed from a dedicated settings page
- streaming retries remain limited to the period before the first chunk
