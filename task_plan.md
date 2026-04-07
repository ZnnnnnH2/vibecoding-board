# Task Plan: OpenAI-Compatible Local Aggregation Proxy

## Goal
Build a local OpenAI-compatible proxy that aggregates multiple upstream relay providers behind one local endpoint, supports `/v1/chat/completions`, `/v1/responses`, `/v1/models`, supports streaming, performs config-driven failover across upstreams, and exposes a built-in admin UI for managing providers, viewing recent request routing records, running manual health checks, and reviewing request statistics.

## Current Phase
Phase 5

## Phases

### Phase 1: Requirements & Discovery
- [x] Understand user intent
- [x] Identify constraints and requirements
- [x] Document findings in `findings.md`
- **Status:** complete

### Phase 2: Planning & Structure
- [x] Define technical approach
- [x] Define routing, failover, and streaming behavior
- [x] Write approved design spec
- [x] User reviews written spec
- **Status:** complete

### Phase 3: Implementation
- [x] Create project structure
- [x] Implement config loading and provider registry
- [x] Implement routing, forwarding, and failover behavior
- [x] Implement API endpoints
- [x] Implement admin APIs, config writeback, and runtime hot reload
- [x] Implement the frontend admin SPA and static serving
- **Status:** complete

### Phase 4: Testing & Verification
- [x] Add unit tests for routing and failover logic
- [x] Add integration tests for non-stream and stream behavior
- [x] Run manual verification against a real OpenAI-compatible client
- [x] Verify admin API mutation flows and request logging
- [x] Verify frontend build and static serving
- **Status:** complete

### Phase 5: Delivery
- [x] Review deliverables
- [x] Summarize usage and limitations
- [x] Hand off the implementation
- **Status:** complete

## Key Questions
1. Which protocol family should the first version support?
Answer: Only OpenAI-compatible upstreams.
2. Which API surfaces must be supported in the first version?
Answer: `/v1/chat/completions`, `/v1/responses`, `/v1/models`, and a local `/healthz`.
3. How should streaming failover work?
Answer: Retry on another upstream only before the first streamed chunk is sent to the client.

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| Use `FastAPI` + `httpx` | Good control over API compatibility, retry logic, and streaming behavior with minimal complexity |
| Keep state in memory and config in a local YAML file | First version should stay simple and local-only |
| Use priority-based failover instead of load balancing | Matches the user's goal of stable fallback with predictable routing |
| Treat `429`, `5xx`, timeouts, and connection failures as retryable | These indicate transient upstream availability issues |
| Treat `400`, `401`, `403`, and `404` as non-retryable | These usually indicate request or credential problems and should be surfaced directly |
| Return the union of enabled upstream models from `/v1/models` | Gives the client one aggregated model list |
| Use `httpx.ASGITransport` in tests | Allows endpoint-level integration tests without real network calls |
| Keep wildcard providers out of `/v1/models` output unless explicit models are listed | Prevents the proxy from advertising fake or guessed model names |
| Add a React + Vite admin SPA served by FastAPI | Provides a visual local control surface without adding a second deploy target |
| Persist provider mutations to `config.yaml` and hot-reload runtime state | Makes UI actions survive restarts without requiring manual service restarts |
| Keep recent request routing records in memory only | Satisfies the user's observability request without introducing persistence infrastructure |
| Keep provider health check results in memory only | Matches the user's local-tool workflow and avoids mixing checks into persistent config or usage stats |
| Aggregate token, latency, and TTFB statistics on the backend | Keeps the dashboard logic simple and ensures one consistent statistical definition |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Missing `writing-plans` skill referenced by brainstorming workflow | 1 | Fallback to `planning-with-files` for persistent task tracking and implementation planning |
| Subagent-based spec review is not permitted in this turn | 1 | Use self-review and surface the written spec to the user for review |
| First `apply_patch` payload failed because the patch was too large for the Windows path/tooling boundary | 1 | Split the implementation into smaller patches |
| `pytest` initially resolved to a different Python environment than the one used for dependency install | 1 | Run tests with `python -m pytest` |
| Frontend `npm install` initially failed because npm tried to write to the global cache directory | 1 | Re-ran install with `--cache .npm-cache` inside the repo |
