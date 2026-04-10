# Provider List Order And Unified Notifications Design

## Goal
Refine the admin provider experience so the list reads more naturally and user feedback is consistent across provider actions.

The new behavior should:
- show disabled providers after enabled providers in the provider list, even when a disabled provider has a higher routing priority
- make the `Preferred` / `首选` marker in the `Providers` table more visually distinct
- replace the page-level flash banner pattern with a unified notification layer
- show healthcheck results in a modal dialog instead of rendering a transient message in a fixed page location

## Scope

In scope:
- provider list ordering for the admin UI
- `Preferred` marker styling in the `Providers` table only
- unified frontend notification primitives for toast and modal feedback
- moving healthcheck feedback to a result dialog
- keeping delete confirmation inside the same dialog management layer

Out of scope:
- changing backend routing behavior
- changing overview or sidebar styling for the preferred provider
- redesigning the provider table structure
- changing admin API response payloads

## Recommended Approach
Introduce a small notification system at the app shell level and keep provider-list ordering as a pure formatting concern.

This keeps behavior changes local to the frontend:
- sorting stays in `format.ts`
- notification orchestration stays in `App.tsx`
- provider table rendering stays in `ProvidersView.tsx`
- visual treatment stays in CSS

## Provider List Ordering

Sorting rules for provider lists used by the admin UI:

1. enabled providers first
2. disabled providers second
3. within each group, sort by `priority` ascending
4. break ties by provider name ascending

Effect:
- disabled providers no longer jump to the top just because they have a smaller numeric priority
- active routing candidates stay grouped together for operational work

This is a presentation-only change. It does not affect backend runtime routing.

## Preferred Marker Styling

Only the `Providers` table preferred marker changes.

Design intent:
- give the current preferred provider a more intentional visual anchor
- increase contrast versus ordinary status pills
- keep the scope narrow so `Overview` and sidebar summaries remain unchanged

Implementation direction:
- add a dedicated preferred pill class rather than reusing the generic primary pill everywhere
- keep the existing table layout and wording

## Unified Notifications

Replace the current page-level flash banner with a unified shell-level notification system that supports:

- `toast`
  - non-blocking success or error feedback for routine mutations
  - auto-dismiss after a short delay
- `dialog-confirm`
  - blocking confirmation for destructive actions such as deleting a provider
- `dialog-result`
  - blocking informational result dialogs for actions that deserve focused review, starting with provider healthchecks

Behavior rules:
- only one dialog is open at a time
- toasts do not block page interaction
- routine mutations use toasts by default
- healthchecks use a result dialog instead of a toast or page banner

## Healthcheck Result Flow

Healthcheck interaction becomes:

1. user clicks `Check`
2. button enters loading state
3. request succeeds or fails and dashboard state updates normally
4. a healthcheck result dialog opens with focused feedback

Dialog content should include:
- provider name
- pass/fail status
- model
- upstream status code
- latency
- error text when present

The dialog only needs a dismiss action. It does not trigger a second mutation.

## Component Boundaries

Expected frontend changes:
- `web/src/format.ts`
  - update provider sorting rules
- `web/src/App.tsx`
  - replace flash-banner state with unified notification state
  - route routine mutations to toast feedback
  - route healthcheck completion to result dialog feedback
- `web/src/components/ProvidersView.tsx`
  - keep table layout
  - apply dedicated preferred styling in the providers list
- `web/src/components/ConfirmDialog.tsx`
  - reuse or adapt under the unified dialog controller
- `web/src/components/`
  - add a toast component and a result dialog component
- `web/src/i18n.tsx`
  - add notification and healthcheck-result copy in English and Chinese
- `web/src/index.css`
  - add toast styles
  - add result dialog styles
  - add preferred-pill styling scoped to the providers table
  - remove reliance on page-level flash banner placement

## Testing And Verification

Frontend verification:
- `cd web; npm run lint`
- `cd web; npm run build`

Manual checks:
- disabled providers render after enabled providers
- preferred marker is visually distinct in the providers table
- ordinary mutations show toasts instead of page banner text
- healthcheck completion opens a result dialog
- delete confirmation still works through the unified dialog layer

## Approval State
This design reflects the user-approved direction on 2026-04-10:
- disabled providers should render after active providers in the list
- only the `Providers` table preferred marker should get the stronger visual treatment
- healthcheck feedback should be shown as a modal dialog
- the frontend should move to a unified notification system instead of page-level flash messaging
