# Findings & Decisions

## Requirements
- The proxy runs locally and exposes one stable endpoint to the user's client applications.
- The first version supports only OpenAI-compatible upstream relay providers.
- The proxy must support `/v1/chat/completions`.
- The proxy must support `/v1/responses`.
- The proxy must support `/v1/models`.
- The proxy must support streaming requests and responses.
- The proxy must fail over automatically when an upstream is unavailable.
- The proxy should be configured from a local file rather than a database or admin UI.

## Research Findings
- The repository is currently minimal and does not constrain the implementation approach.
- `FastAPI` plus `httpx` is a practical fit for a local HTTP proxy with JSON and streaming support.
- Streaming failover cannot be seamless after the first chunk has been sent to the client because the response has already started.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Use a single application-layer proxy service | Easier to implement and debug than Nginx/OpenResty for API-aware failover |
| Keep the proxy as transparent as possible | Minimizes compatibility bugs with existing OpenAI-compatible clients |
| Use model filtering plus provider priority for routing | Simple, predictable, and sufficient for the first version |
| Use in-memory circuit breaker state | Avoids unnecessary infrastructure in a local-first tool |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Brainstorming workflow references tools or skills not available in this session | Recorded the gap and continued with the closest allowed workflow |

## Resources
- `README.md`
- `pyproject.toml`
- `main.py`
- `docs/superpowers/specs/2026-04-07-openai-aggregator-proxy-design.md`
- `C:/Users/znnnnnh2/.codex/skills/brainstorming/SKILL.md`
- `C:/Users/znnnnnh2/.codex/skills/planning-with-files/skills/planning-with-files/SKILL.md`

## Visual/Browser Findings
- No browser or image-based research was required for this design task.
