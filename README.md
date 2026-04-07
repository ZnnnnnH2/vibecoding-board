# OpenAI-Compatible Local Aggregation Proxy

This project runs a local `FastAPI` proxy in front of multiple OpenAI-compatible upstream relays. Your client points at one local endpoint, and the proxy chooses an upstream based on model support, priority, and temporary health state.

## What it supports

- `POST /v1/chat/completions`
- `POST /v1/responses`
- `GET /v1/models`
- `GET /healthz`
- Streaming with failover before the first chunk
- Non-streaming failover on timeout, connection errors, `429`, and `5xx`
- Priority-based routing with a simple circuit breaker
- Built-in admin UI at `/admin`
- Persistent provider management with config writes and hot reload
- In-memory recent request history showing provider, URL, model, request type, status, and failover attempts
- Manual per-provider health checks from the admin UI
- Visual provider stats for request count, success rate, latency, first-byte time, and token totals

## What it does not do

- Non-OpenAI protocol translation
- Load balancing
- Database-backed state
- Mid-stream failover after output has already started
- Persistent request analytics or database-backed history

## Quick start

1. Install dependencies.
2. Copy `config.example.yaml` to `config.yaml`.
3. Replace upstream URLs and configure your keys.
4. Start the proxy.

Example:

```powershell
uv sync --extra dev
Copy-Item config.example.yaml config.yaml
$env:RELAY_A_API_KEY="your-key-a"
$env:RELAY_B_API_KEY="your-key-b"
uv run vibecoding-board --config config.yaml
```

Default listen address:

- `http://127.0.0.1:9000`

Point your OpenAI-compatible client at:

- `http://127.0.0.1:9000/v1`

Open the admin UI at:

- `http://127.0.0.1:9000/admin/`

## Admin UI

The admin UI supports:

- adding providers
- editing providers
- deleting providers
- promoting a provider to global primary
- enabling and disabling providers
- running a manual health check against a single provider
- viewing aggregated provider usage statistics
- viewing recent in-memory request routing records

Behavior notes:

- all management changes write back to `config.yaml`
- successful saves hot-reload the running proxy
- recent request records are memory only and are cleared when the process stops
- existing API keys are never sent back to the browser; edit forms keep the old key when left blank
- health checks do not get mixed into request statistics
- token statistics only include requests where the upstream returned usage fields explicitly

## Config

See [config.example.yaml](/D:/Codes/vibecoding-board/config.example.yaml).

Important notes:

- `base_url` should point at the upstream API root, usually ending in `/v1`
- lower `priority` values are tried first
- `models: ["*"]` allows routing any model to that provider
- if a provider uses `models: ["*"]`, set `healthcheck_model` so the admin UI knows which model to probe
- `/v1/models` only advertises explicit model names; wildcard-only providers are not expanded automatically

## Frontend Development

The built admin app is already served from `vibecoding_board/static/admin`, so normal use does not require Node.js commands.

If you want to iterate on the frontend source:

```powershell
cd web
npm install --cache .npm-cache
npm run build
```

Optional dev server:

```powershell
cd web
npm install --cache .npm-cache
npm run dev
```

## Tests

```powershell
uv run pytest
```

Frontend build verification:

```powershell
cd web
npm run build
```

## Design

The approved design document is at [2026-04-07-openai-aggregator-proxy-design.md](/D:/Codes/vibecoding-board/docs/superpowers/specs/2026-04-07-openai-aggregator-proxy-design.md).
