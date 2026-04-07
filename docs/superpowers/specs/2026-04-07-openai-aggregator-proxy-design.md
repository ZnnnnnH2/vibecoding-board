# OpenAI-Compatible Local Aggregation Proxy Design

## 1. Goal
Create a local proxy service that exposes one stable OpenAI-compatible endpoint while routing requests across multiple upstream relay providers. The first version focuses on operational simplicity: one local service, one local config file, in-memory health state, and predictable priority-based failover.

## 2. Scope

In scope:
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/models`
- `GET /healthz`
- Streaming and non-streaming requests
- Config-driven upstream selection
- Automatic retry and failover across upstreams
- Circuit breaker behavior for unstable upstreams
- Structured logging without leaking secrets

Out of scope:
- Native support for non-OpenAI protocols such as Anthropic or Gemini
- Load balancing across healthy upstreams
- Persistent storage or a database
- Web UI or management console
- Mid-stream failover after output has already started
- Cross-protocol translation or request schema rewriting

## 3. Recommended Approach
Use `FastAPI` as the HTTP application layer and `httpx` as the upstream HTTP client.

Why this approach:
- The proxy must be protocol-aware enough to handle routing, retry policy, and stream lifecycle decisions.
- A Python application layer is easier to evolve than a pure reverse proxy configuration.
- The repository is currently minimal, so a focused service is the shortest path to a maintainable first version.

Alternatives considered:
1. A generic provider abstraction layer for multiple API families. Rejected for the first version because it would over-design a strictly OpenAI-compatible proxy.
2. Nginx or OpenResty. Rejected because request-aware failover and stream handling would be harder to implement and debug.

## 4. Architecture

The service is split into five modules:

1. API layer
Handles incoming OpenAI-compatible routes and validates the minimum request requirements.

2. Router
Chooses candidate upstreams based on model support, enabled status, priority, and circuit breaker state.

3. Provider registry
Loads upstream definitions from config and keeps in-memory health state such as failure counters and cooldown windows.

4. Forwarder
Forwards the request to the selected upstream, manages headers and body pass-through, and relays normal or streaming responses to the client.

5. Health and failover logic
Classifies errors, increments failure counters, trips circuit breakers, and decides whether another upstream should be attempted.

## 5. External API Behavior

### 5.1 Supported endpoints
- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/models`
- `GET /healthz`

### 5.2 General request handling
- The proxy expects JSON request bodies for `chat/completions` and `responses`.
- The request must include a `model` field.
- The proxy forwards the request body as-is whenever possible.
- The proxy removes or replaces only the minimal set of headers needed for safe forwarding, especially `Authorization`.

### 5.3 `/v1/models`
- Returns the union of models from all enabled upstreams that are configured as available.
- The first version may optionally add simple metadata describing which upstreams claim each model, but the default behavior should stay close to OpenAI-compatible responses.

### 5.4 `/healthz`
- Returns whether the local proxy process is healthy.
- It does not attempt to represent the live health of every upstream in the health check response.

## 6. Configuration Model

The first version uses a local YAML configuration file.

Example shape:

```yaml
listen:
  host: 127.0.0.1
  port: 9000

providers:
  - name: relay_a
    base_url: https://example-a.test/v1
    api_key: env:RELAY_A_API_KEY
    enabled: true
    priority: 10
    models: ["gpt-4.1", "gpt-4o-mini"]
    timeout_seconds: 60
    max_failures: 3
    cooldown_seconds: 30

  - name: relay_b
    base_url: https://example-b.test/v1
    api_key: env:RELAY_B_API_KEY
    enabled: true
    priority: 20
    models: ["*"]
    timeout_seconds: 60
    max_failures: 3
    cooldown_seconds: 30
```

Required provider fields:
- `name`
- `base_url`
- `api_key`
- `enabled`
- `priority`
- `models`
- `timeout_seconds`
- `max_failures`
- `cooldown_seconds`

Behavioral notes:
- Lower `priority` means higher preference.
- `models: ["*"]` means the provider is eligible for any requested model.
- `api_key` may later support environment variable indirection, but the first version only needs one reliable approach.

## 7. Routing Rules

The routing algorithm is intentionally simple:

1. Read the requested `model`.
2. Build the list of providers that:
   - are enabled
   - support the requested model
   - are not currently inside an active circuit-breaker cooldown window
3. Sort candidates by ascending `priority`.
4. Attempt providers in order until a response is successfully established or the candidate list is exhausted.

This is failover, not load balancing. Healthy higher-priority providers always win unless they are temporarily excluded.

## 8. Streaming Behavior

Streaming is supported when the incoming request includes `stream: true`.

Rules:
- If the selected upstream fails before the first response chunk is sent to the client, the proxy may retry another eligible upstream.
- Once the proxy has started sending streamed data to the client, the response is considered committed.
- If the upstream stream fails after the first chunk, the proxy does not switch to another upstream mid-stream.

Reasoning:
- Mid-stream failover cannot be made transparent because the client has already received partial output from the previous upstream.

## 9. Error Classification and Failover Policy

Retryable errors:
- connection failures
- upstream timeouts
- HTTP `429`
- HTTP `5xx`

Non-retryable errors:
- HTTP `400`
- HTTP `401`
- HTTP `403`
- HTTP `404`

Policy:
- On retryable failure, increment the provider's consecutive failure counter and try the next eligible provider if the response has not yet been committed.
- On non-retryable failure, return the upstream response directly to the client without trying other providers.
- If all eligible providers fail with retryable conditions, return a local aggregated error describing that all candidate upstreams failed.

## 10. Circuit Breaker Behavior

Each provider maintains:
- consecutive failure count
- circuit state
- cooldown-until timestamp

State rules:
- Success resets the consecutive failure count.
- A retryable failure increments the consecutive failure count.
- When the count reaches `max_failures`, the provider enters the open state and is skipped until `cooldown_seconds` expires.
- After cooldown expiry, the provider is allowed back into routing as a probe attempt.
- If the probe succeeds, the provider returns to normal.
- If the probe fails, the provider re-enters cooldown.

## 11. Logging and Observability

Each request should log:
- endpoint
- requested model
- selected provider
- whether failover occurred
- final status code
- total latency

Secrets and sensitive payloads must not be logged:
- no API keys
- no full prompt or message content by default

The first version does not need metrics or tracing infrastructure.

## 12. Testing Strategy

Unit tests:
- model matching
- provider prioritization
- retryable vs non-retryable error classification
- circuit breaker open and recovery behavior

Integration tests with mock upstreams:
- non-stream request succeeds on first provider
- non-stream request fails over to second provider
- stream request fails before first chunk and successfully retries
- stream request fails after first chunk and does not retry
- `/v1/models` returns the expected aggregate view

Manual verification:
- point a real OpenAI-compatible client at the local proxy
- verify `chat/completions` works
- verify `responses` works
- verify a forced upstream outage triggers failover as designed

## 13. File and Module Direction

The exact file layout can be finalized during implementation planning, but the first version should keep these concerns separate:
- application entrypoint
- config models and loading
- provider state registry
- router and error classification
- forwarding logic
- API handlers
- tests

## 14. Constraints and Non-Goals

The design optimizes for a single-user or small local deployment. It does not attempt to be a production multi-tenant gateway. Avoiding unnecessary abstraction is an explicit goal of the first version.

## 15. Approval State

This document reflects the design approved in chat on 2026-04-07:
- OpenAI-compatible upstreams only
- `chat/completions` and `responses` support
- streaming support with failover only before the first chunk
- priority-based failover rather than load balancing
