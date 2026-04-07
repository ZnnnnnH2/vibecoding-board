# Admin Shell Refactor Design

## 1. Goal
Refactor the admin frontend into a clearer management console that borrows the information density of `one-api` and `new-api` plus the overview discipline of `LiteLLM`, while preserving the current lightweight backend and runtime model.

The new UI should make three workflows faster:
- understanding current proxy health at a glance
- managing providers with less friction
- inspecting recent traffic without mixing it into provider editing

## 2. Scope

In scope:
- a new admin shell with left navigation and top toolbar
- three views: `Overview`, `Providers`, and `Traffic`
- a denser provider management experience
- inline priority editing from the provider list
- grouped provider create/edit form sections
- manual refresh only
- reuse of the existing admin API contract where possible

Out of scope:
- multi-tenant features
- auth, RBAC, or user management
- websocket updates or polling
- batch key import
- route library adoption
- backend data-model redesign

## 3. Design Direction

### 3.1 Reference mix
- `one-api` / `new-api`: dense operational table, filter-first management flow, grouped forms
- `LiteLLM`: cleaner overview hierarchy, stronger summary layer, better distinction between overview and drill-down screens

### 3.2 Product fit
This project is still a local single-user proxy rather than a full gateway platform. The frontend should therefore feel like a capable control plane, not a large SaaS admin. The refactor should improve structure and efficiency without introducing platform-only complexity.

## 4. Information Architecture

### 4.1 Shell
The application becomes a shell layout with:
- left sidebar navigation
- top toolbar
- central content region

### 4.2 Views

#### Overview
Purpose: rapid system understanding in a few seconds.

Content:
- global KPI cards
- runtime status panel
- provider health snapshot
- recent traffic preview

#### Providers
Purpose: operational management workspace.

Content:
- search and filters
- dense provider table
- inline priority editing
- row actions for edit, enable/disable, make primary, healthcheck, delete
- shared add/edit drawer

#### Traffic
Purpose: request inspection and debugging.

Content:
- filter bar
- traffic table or structured list
- expandable request details

## 5. Visual Direction

Replace the current single-page atmospheric card wall with a calmer admin style:
- lower visual noise
- stronger layout hierarchy
- color used mainly for state and emphasis
- reduced background effects
- restrained motion only for navigation, drawers, and expansions

The interface should feel precise and operational rather than decorative.

## 6. Component Strategy

### Rewrite
- `web/src/App.tsx`
- main layout styles in `web/src/index.css`
- provider management surface
- traffic browsing surface

### Preserve and adapt
- `web/src/api.ts`
- `web/src/types.ts`
- current backend dashboard and mutation response shape
- provider drawer field model, with better structure and layout

## 7. Data Flow Rules

- Load `/admin/api/dashboard` once on initial render.
- Load `/admin/api/dashboard` again only when the user presses refresh.
- All successful mutations replace local UI state with the returned `dashboard`.
- Filters and view-specific search are client-side only.
- Traffic inspection is read-only and does not trigger detail fetches.

This keeps state management simple while still supporting a more professional shell.

## 8. Interaction Rules

### Providers
- Priority edits save on blur.
- Inline edit failures revert the displayed value and show a flash error.
- Row actions remain immediate and operate against the current row.

### Overview
- Overview is summary-first and should not become a second management page.
- Cards or summary rows may navigate into `Providers` or `Traffic`.

### Traffic
- Traffic remains request-history focused.
- Expanded rows show attempts, usage, latency, and final error details.

## 9. Implementation Plan

### Phase 1: Shell
- introduce sidebar navigation and top toolbar
- split the page into `Overview`, `Providers`, `Traffic` view states

### Phase 2: Providers
- replace provider cards with a denser table
- integrate inline priority editing
- reorganize the add/edit drawer into grouped sections

### Phase 3: Overview and Traffic
- build KPI and runtime summary panels
- convert traffic view into a dedicated inspection surface

### Phase 4: Polish and verification
- unify styles across tables, filters, buttons, drawers, and states
- rebuild static assets
- run frontend and backend verification

## 10. Risks and Constraints

- A full visual rewrite can regress usability if the shell and content density are changed at the same time. The work should stay phased.
- The current codebase is small, so over-abstraction would be a mistake.
- Because there is no route library, view transitions should stay simple and explicit.

## 11. Approval State

Approved in chat on 2026-04-08:
- mixed inspiration from `one-api`, `new-api`, and `LiteLLM`
- shell layout with sidebar and top bar
- three views only: `Overview`, `Providers`, `Traffic`
- manual refresh only
- phased implementation rather than a single giant rewrite
