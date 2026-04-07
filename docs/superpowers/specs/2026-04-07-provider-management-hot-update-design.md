# Provider Management Hot Update Design

## Goal
Improve the admin experience for managing upstream providers without changing the proxy's lightweight architecture. The focus is fast operational edits: hot-add a provider, hot-update routing priority, and avoid unnecessary dashboard polling.

## Scope
In scope:
- hot-add providers from the admin UI
- inline priority editing from the provider list
- config write-through with immediate runtime activation
- manual dashboard refresh only
- a denser form layout inspired by `one-api`

Out of scope:
- channel-type abstractions
- batch key import
- background polling or automatic dashboard refresh
- database-backed management state

## Recommended Approach
Keep the existing FastAPI runtime manager and config-backed persistence model. Add one narrow mutation endpoint for priority updates and let every successful write return the latest dashboard payload. The frontend should treat mutation responses as the source of truth and only fetch `/admin/api/dashboard` on initial page load or explicit user refresh.

## Backend Design
- Add `PATCH /admin/api/providers/{provider_name}/priority`.
- Implement a dedicated `RuntimeManager.update_provider_priority()` method.
- Reuse the current atomic config save path and runtime snapshot rebuild.
- Preserve current routing semantics: lower `priority` means earlier selection, and ties are still resolved by provider name.

## Frontend Design
- Keep the existing admin dashboard structure, but make provider cards more operational.
- Add an inline priority input to each provider card.
- Save priority on blur, matching the direct-edit feel of `one-api`.
- Keep full create/edit in a shared drawer, but reorganize fields into grouped sections:
  - identity
  - routing
  - reliability
- Remove unnecessary refresh orchestration logic. The dashboard is loaded once on mount and only again when the user clicks refresh.

## Approval State
Approved in chat on 2026-04-07:
- preserve the current architecture
- borrow form ergonomics from `one-api`
- update priority inline on blur
- do not add high-frequency frontend polling
