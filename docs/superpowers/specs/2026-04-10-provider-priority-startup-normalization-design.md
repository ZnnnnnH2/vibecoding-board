# Provider Priority Startup Normalization Design

## Goal
Ensure provider priorities are normalized automatically when the backend starts so routing order is stable and the persisted config matches the effective runtime order.

The new behavior should:
- sort providers by their current `priority` value in descending order before renumbering
- reassign priorities as `10, 0, -10, -20 ...`
- write the normalized priorities back to `config.yaml` during startup when the loaded config is not already normalized
- preserve existing runtime routing semantics and admin mutation APIs

## Scope

In scope:
- startup-time provider priority normalization
- config write-back when normalized priorities differ from the loaded config
- tests for config persistence and effective routing order after startup

Out of scope:
- changing the meaning of provider priority
- changing admin API payloads or frontend behavior
- changing manual priority editing semantics outside startup normalization
- adding a new config switch for this behavior

## Recommended Approach
Run normalization inside `RuntimeManager.initialize()`, immediately after loading the config and before building the runtime snapshot.

This keeps the behavior at the runtime boundary where startup activation already happens, while leaving `ConfigStore` as a thin persistence layer. It also ensures the dashboard, request routing, and saved config all reflect the same normalized ordering from the first request onward.

## Normalization Rules

Input ordering:
- sort providers by current `priority` descending before renumbering
- break ties by provider name descending so the final normalized routing order still matches the current `(priority asc, name asc)` selection behavior

Output numbering:
- first provider gets `10`
- each next provider decreases by `10`
- example: `10, 0, -10, -20`

Persistence:
- if the normalized priorities differ from the loaded config, save the normalized config back to the same `config.yaml` path before runtime activation completes
- if priorities already match the normalized sequence, do not perform an unnecessary write

## Runtime Design

Backend startup flow becomes:

1. load `ProxyConfig` from disk
2. normalize provider priorities using the loaded values as sort input
3. save the normalized config if it changed
4. build the runtime snapshot from the normalized config
5. expose the normalized config to the dashboard and request router

Why this layer:
- `create_app()` already delegates startup state construction to `RuntimeManager.initialize()`
- the runtime manager already owns config activation and config-backed mutations
- the rule is business behavior, not storage behavior, so it fits better here than in `ConfigStore`

## Compatibility and Edge Cases

- Negative priorities remain valid input. They only affect the initial sort order before normalization.
- Duplicate priorities remain valid input. Ties are resolved so the final normalized routing order stays consistent with the current selection logic.
- Manual admin priority updates still write the requested value immediately. The next restart may renumber providers again based on the saved numeric order.
- Existing configs remain loadable without schema changes.

## Testing Strategy

Backend tests:
- startup rewrites a non-normalized config to `10, 0, -10 ...`
- startup preserves the same provider preference order after normalization
- request routing after startup follows the normalized order, not the original raw numbers
- already normalized configs do not change effective order

## Files Expected to Change
- `vibecoding_board/config.py`
- `vibecoding_board/runtime.py`
- `tests/test_admin_api.py`

## Approval State
This design reflects the user-approved direction on 2026-04-10:
- normalize on backend startup
- sort by current `priority` numeric value in descending order before renumbering
- assign normalized priorities as `10, 0, -10, -20 ...`
- write the normalized priorities back to `config.yaml`
