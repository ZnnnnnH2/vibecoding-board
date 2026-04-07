# Task Plan: OpenAI-Compatible Local Aggregation Proxy

## Goal
Build a local OpenAI-compatible proxy that aggregates multiple upstream relay providers behind one local endpoint, supports `/v1/chat/completions`, `/v1/responses`, `/v1/models`, supports streaming, and performs config-driven failover across upstreams.

## Current Phase
Phase 2

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
- [ ] User reviews written spec
- **Status:** in_progress

### Phase 3: Implementation
- [ ] Create project structure
- [ ] Implement config loading and provider registry
- [ ] Implement routing, forwarding, and failover behavior
- [ ] Implement API endpoints
- **Status:** pending

### Phase 4: Testing & Verification
- [ ] Add unit tests for routing and failover logic
- [ ] Add integration tests for non-stream and stream behavior
- [ ] Run manual verification against a real OpenAI-compatible client
- **Status:** pending

### Phase 5: Delivery
- [ ] Review deliverables
- [ ] Summarize usage and limitations
- [ ] Hand off the implementation
- **Status:** pending

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

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| Missing `writing-plans` skill referenced by brainstorming workflow | 1 | Fallback to `planning-with-files` for persistent task tracking and implementation planning |
| Subagent-based spec review is not permitted in this turn | 1 | Use self-review and surface the written spec to the user for review |
