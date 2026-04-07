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
- The project now needs a built-in admin UI for visual provider management.
- Admin actions must support add, edit, delete, enable/disable, and global primary switching.
- Admin changes must write back to `config.yaml` and hot-reload the running runtime.
- The UI must show recent request routing records, but those records only need in-memory retention.
- The UI must support a button-driven manual health check per provider.
- The UI must expose visual usage statistics, including token totals and first-byte timing.

## Research Findings
- The repository is currently minimal and does not constrain the implementation approach.
- `FastAPI` plus `httpx` is a practical fit for a local HTTP proxy with JSON and streaming support.
- Streaming failover cannot be seamless after the first chunk has been sent to the client because the response has already started.
- In `httpx 0.28`, per-request stream timeouts belong on `build_request(..., timeout=...)`, not `AsyncClient.send(...)`.
- `httpx.ASGITransport` is sufficient for end-to-end proxy tests against fake upstream applications.
- `uv sync --extra dev` created a project-local `.venv` using CPython 3.12.12 and produced `uv.lock`.
- `npm install` can be kept inside the workspace by pointing npm cache at `web/.npm-cache`.
- The built Vite app can be emitted directly into `vibecoding_board/static/admin`, which lets FastAPI serve `/admin` without a second deploy step.
- The current environment has unstable permissions around auto-generated pytest temp and cache directories, so explicit file-list test runs are the most reliable verification path here.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Use a single application-layer proxy service | Easier to implement and debug than Nginx/OpenResty for API-aware failover |
| Keep the proxy as transparent as possible | Minimizes compatibility bugs with existing OpenAI-compatible clients |
| Use model filtering plus provider priority for routing | Simple, predictable, and sufficient for the first version |
| Use in-memory circuit breaker state | Avoids unnecessary infrastructure in a local-first tool |
| Add a small CLI wrapper around the FastAPI app | Lets the user start the proxy with `python main.py --config config.yaml` |
| Return OpenAI-style JSON errors from the proxy layer | Keeps client-side behavior more predictable on local validation and aggregate upstream failures |
| Add a `build-system` section for `uv` packaging | Lets `uv sync` install the local package and expose the CLI script inside `.venv` |
| Use `uv` as the documented workflow | Avoids further global environment contamination |
| Use a mutable runtime manager plus atomic config store | Supports safe config writes and hot-reload while requests continue using their current snapshot |
| Add a bounded in-memory request log store | Gives the admin UI recent routing visibility without persisting user traffic |
| Build the UI with React 19 and Vite | Fast enough to implement, modern enough for a polished SPA, and easy to bundle into the backend |
| Add `healthcheck_model` for wildcard providers | Lets the admin UI probe real inference without guessing a model name |
| Compute usage stats only from explicit upstream usage payloads | Avoids misleading token estimates |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Brainstorming workflow references tools or skills not available in this session | Recorded the gap and continued with the closest allowed workflow |
| Initial all-in-one patch was rejected by the tool on Windows | Re-applied the implementation in smaller patches |
| Shell `pytest` resolved to a different Python environment | Switched to `python -m pytest` for consistent dependency resolution |
| Initial implementation validation used global `pip` by mistake | Removed the global editable install and moved validation to `uv sync` and `uv run` only |
| `npm install` failed under the default global cache path | Redirected npm cache to `web/.npm-cache` inside the repo |
| Temporary and cache directories created by pytest had unstable permissions in this environment | Switched verification to explicit test file lists and removed tmp_path dependence in tests |

## Resources
- `README.md`
- `pyproject.toml`
- `main.py`
- `config.example.yaml`
- `vibecoding_board/app.py`
- `vibecoding_board/config.py`
- `vibecoding_board/registry.py`
- `vibecoding_board/service.py`
- `vibecoding_board/cli.py`
- `vibecoding_board/runtime.py`
- `vibecoding_board/config_store.py`
- `vibecoding_board/request_log.py`
- `vibecoding_board/admin_api.py`
- `vibecoding_board/static/admin/`
- `tests/test_api.py`
- `tests/test_admin_api.py`
- `tests/test_admin_ui.py`
- `tests/test_registry.py`
- `web/package.json`
- `web/vite.config.ts`
- `web/src/App.tsx`
- `web/src/index.css`
- `web/src/components/ProviderCard.tsx`
- `web/src/components/ProviderDrawer.tsx`
- `web/src/components/ConfirmDialog.tsx`
- `docs/superpowers/specs/2026-04-07-openai-aggregator-proxy-design.md`
- `C:/Users/znnnnnh2/.codex/skills/brainstorming/SKILL.md`
- `C:/Users/znnnnnh2/.codex/skills/planning-with-files/skills/planning-with-files/SKILL.md`

## Visual/Browser Findings
- No browser or image-based research was required for this design task.
