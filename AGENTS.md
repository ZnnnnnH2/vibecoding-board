# Repository Guidelines

## Project Structure & Module Organization
`vibecoding_board/` contains the FastAPI proxy, runtime/config handling, and the packaged admin assets served at `/admin`. Keep backend changes inside focused modules such as `app.py`, `service.py`, `runtime.py`, and `admin_api.py`. `tests/` holds backend `pytest` coverage, and `test-workspaces/` is used for temporary filesystem fixtures during tests. Frontend source lives in `web/src/`; treat `vibecoding_board/static/admin/` as generated output and rebuild it instead of editing bundled assets by hand. Design notes live under `docs/superpowers/specs/`.

## Build, Test, and Development Commands
Use `uv` for Python workflows:

- `uv sync --extra dev` installs runtime and test dependencies.
- `uv run vibecoding-board --config config.yaml` starts the local proxy and serves the built admin UI.
- `uv run pytest` runs the backend test suite.

Use Node only when changing the admin UI:

- `cd web; npm install --cache .npm-cache` installs frontend dependencies locally.
- `cd web; npm run dev` starts the Vite dev server.
- `cd web; npm run build` rebuilds `vibecoding_board/static/admin/`.
- `cd web; npm run lint` runs ESLint for the TypeScript/React app.

## Coding Style & Naming Conventions
Follow existing style: 4-space indentation and `snake_case` for Python functions, modules, and tests; `PascalCase` for React components; `camelCase` for TypeScript variables and props. Prefer small, single-purpose modules over large mixed-responsibility files. Keep imports explicit, preserve type hints in Python, and use the existing ESLint config in `web/eslint.config.js`. No backend formatter is configured here, so match the surrounding file style closely.

## Testing Guidelines
Add or update `pytest` coverage for backend behavior changes, especially routing, failover, config mutation, and admin API flows. Name tests `test_<behavior>.py` and keep fixtures deterministic; current tests write temporary state under `test-workspaces/`. For frontend changes, run `npm run build` and `npm run lint` before opening a PR.

## Commit & Pull Request Guidelines
The current history uses lowercase Conventional Commit style, for example `docs: add local aggregation proxy design`. Follow `type: imperative summary` (`feat:`, `fix:`, `docs:`). PRs should explain user-visible behavior, list verification commands, link related issues, and include screenshots for `web/` UI changes.

## Security & Configuration Tips
Do not commit real API keys in `config.yaml`; prefer environment-backed values and keep `config.example.yaml` sanitized. When changing frontend code, rebuild the admin bundle so the served assets and source stay in sync.
