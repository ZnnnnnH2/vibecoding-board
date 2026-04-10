# Provider Always Alive Design

## Goal
Add a provider-level `always_alive` capability so an upstream can stay eligible for routing even after repeated failures would normally place it into cooldown.

The new behavior should:
- add a clear provider-level switch exposed in the admin UI as `Always alive` / `始终存活`
- persist the behavior in config so it survives runtime reloads and process restarts
- keep existing failure accounting and diagnostics intact
- prevent cooldown from removing an `always_alive` provider from the routing candidate set
- keep `enabled` as the stronger gate, so disabled providers still do not receive traffic

## Scope

In scope:
- backend config schema for provider-level `always_alive`
- runtime routing behavior for cooldown suppression
- admin API and dashboard payload updates
- admin UI button for toggling `always_alive`
- provider table copy that explains the behavior
- backend and frontend verification for the new flag

Out of scope:
- changing the global retry-policy model
- redefining `max_failures` or `cooldown_seconds`
- adding a one-off "recover from cooldown" action
- changing provider-selection priority rules
- redesigning the provider drawer or provider table layout

## Recommended Approach
Introduce an explicit boolean field, `always_alive`, on each provider and treat it as a durable routing capability.

This is preferable to overloading existing fields:
- `max_failures=0` would weaken the meaning of a field that currently models a real threshold
- a temporary "clear cooldown" button would not satisfy the requested persistent behavior

The implementation should preserve existing observability:
- failures are still counted
- last error and failure timestamps are still updated
- the provider simply never becomes unavailable because of cooldown while `always_alive=true`

## Behavior Model

### Routing availability

Provider availability should be determined by these rules:

1. if `enabled=false`, the provider is unavailable
2. if `enabled=true` and `always_alive=true`, the provider is available regardless of cooldown state
3. if `enabled=true` and `always_alive=false`, the existing cooldown rules continue to apply

This keeps the mental model simple:
- `enabled` controls whether the provider can ever receive traffic
- `always_alive` controls whether repeated failures can temporarily remove it from routing

### Failure accounting

When `always_alive=true`:
- `consecutive_failures` still increments
- `last_error` still updates
- `last_failure_at` still updates
- `last_success_at` still clears the failure streak on success, as today
- reaching `max_failures` does not set or preserve a blocking `cooldown_until`

This means operators can still see that the provider is unhealthy without the router suppressing it.

### State transition when toggled on

If a provider is already in cooldown and the user enables `always_alive`, the system should clear `cooldown_until` immediately so the provider re-enters routing at once.

This avoids an inconsistent state where the UI claims the provider is "always alive" but runtime selection is still waiting for an old cooldown deadline to expire.

### State transition when toggled off

If `always_alive` is later disabled, the provider returns to the normal cooldown model from that point forward.

No synthetic cooldown should be created retroactively. The next failure sequence should determine whether cooldown is entered, using the same rules as other providers.

## Config And Runtime Design

Add `always_alive: bool = False` to:
- `ProviderConfig`
- `RuntimeProvider`
- any provider snapshot or dashboard representation that reflects provider routing state

Compatibility rules:
- existing configs without the field continue to load, defaulting to `false`
- config serialization should write the field when present in the model dump

Runtime rules:
- the registry should treat `always_alive=true` as a bypass for cooldown-based unavailability
- cooldown bookkeeping may still be cleared proactively when failures are recorded or when the flag is toggled on, but routing behavior must not depend on a cooldown timestamp for always-alive providers

## Admin API Design

Expose the flag in both full provider payloads and a dedicated toggle endpoint.

Expected changes:
- include `always_alive` in create/update provider payload models
- include `always_alive` in dashboard provider summaries
- add `POST /admin/api/providers/{provider_name}/always-alive/toggle`

The dedicated toggle endpoint should mirror the ergonomics of the existing enable/disable action:
- mutate one provider field
- persist config
- rebuild runtime
- return the latest dashboard payload plus a localized success message

Using a focused endpoint keeps the list action cheap and avoids forcing the frontend to reopen the full edit drawer for a single operational toggle.

## Frontend Design

### Provider list action

Add a new provider-table action button:
- when `always_alive=false`: show `Always alive` / `始终存活`
- when `always_alive=true`: show `Disable always alive` / `取消始终存活`

The action should:
- use the same busy-state model as other row actions
- update the dashboard from the mutation response
- surface the existing toast-style mutation feedback

### Provider status copy

The provider table should expose the flag in lightweight operational copy so the behavior is visible without opening edit mode.

Recommended presentation:
- keep the main status derived from enabled/cooling/unsteady/ready
- add a secondary hint in the status or reliability column when `always_alive=true`
- the hint should state that failures do not place this provider into cooldown removal

This keeps the table readable while making the special routing rule discoverable.

### Drawer support

The create/edit drawer should also understand `always_alive` so the value round-trips correctly during full edits.

This does not require a broader drawer redesign. A simple checkbox in the reliability section is sufficient.

## Component Boundaries

Expected backend changes:
- `vibecoding_board/config.py`
  - add `always_alive` to provider config/runtime models
- `vibecoding_board/registry.py`
  - suppress cooldown-based exclusion for always-alive providers
- `vibecoding_board/runtime.py`
  - expose the flag in dashboard payloads
  - add a mutation path for toggling the flag and clearing cooldown when enabled
- `vibecoding_board/admin_api.py`
  - accept and return the flag
  - add the dedicated toggle route
- `vibecoding_board/admin_i18n.py`
  - add localized mutation messages if needed

Expected frontend changes:
- `web/src/types.ts`
  - add `always_alive` to provider summary and form state
- `web/src/api.ts`
  - include the field in create/update payloads
  - add the toggle API call
- `web/src/App.tsx`
  - wire the new action into the shared mutation flow
- `web/src/components/ProvidersView.tsx`
  - add the list action and explanatory copy
- `web/src/components/ProviderDrawer.tsx`
  - add a checkbox for full-form editing
- `web/src/i18n.tsx`
  - add English and Chinese labels and helper text

## Testing And Verification

Backend tests should cover:
- config round-trip with `always_alive` omitted and explicitly enabled
- registry availability: always-alive providers remain candidates after repeated failures
- toggling `always_alive` on clears an existing cooldown
- toggling `always_alive` off restores normal future cooldown behavior
- dashboard payload includes the flag

Frontend verification:
- `cd web; npm run lint`
- `cd web; npm run build`

Backend verification:
- `uv run pytest`

Manual checks:
- a provider marked always alive continues to appear routable after repeated failures
- a provider already cooling becomes routable immediately after enabling always alive
- disabling the provider still removes it from routing
- the admin UI shows the flag clearly in both the list and drawer

## Approval State
This design reflects the user-approved direction on 2026-04-10:
- "always alive" means the provider stays in routing even when repeated failures would normally trigger cooldown
- the next step should be writing the spec before implementation
