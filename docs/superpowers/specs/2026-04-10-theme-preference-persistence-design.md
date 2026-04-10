# Theme Preference Persistence Design

## Goal
Persist the admin theme choice across refreshes while keeping the default behavior aligned with the user's system color scheme.

The new behavior should:
- default to following the operating system theme when no explicit theme preference has been saved
- persist explicit light or dark selections across refreshes
- keep the current lightweight header toggle instead of expanding the UI into a larger theme settings control
- update the effective theme automatically when the system theme changes and the user is still in the default follow-system state

## Scope

In scope:
- frontend theme preference state
- local persistence of the chosen theme preference
- resolving the rendered theme from saved preference plus system theme
- listening for system theme changes while the user is in the default mode

Out of scope:
- backend config or server-side persistence
- adding a new dedicated settings page control for theme selection
- redesigning the existing theme toggle button
- changing unrelated admin notification or provider-management behavior

## Recommended Approach
Introduce a small theme preference abstraction with two levels:

- `themePreference`: `auto | light | dark`
- `resolvedTheme`: `light | dark`

This keeps the user-facing behavior simple while making the implementation explicit:
- `auto` means follow the system theme
- `light` and `dark` mean the user has chosen an override

The header toggle remains a simple dark/light switch, but internally it writes an explicit override once the user interacts.

## State Model

Theme behavior should be driven by:

1. saved preference from local storage
2. system preference from `prefers-color-scheme`
3. derived resolved theme applied to the document root

Rules:
- if there is no saved preference, use `auto`
- if preference is `auto`, resolve theme from the current system setting
- if preference is `light` or `dark`, use that directly
- apply only the resolved theme to `document.documentElement.dataset.theme`

## Persistence

Store the preference in a dedicated frontend key, for example:

```text
admin-theme-preference
```

Behavior:
- load on startup
- validate values and fall back to `auto` when absent or invalid
- save whenever the user changes preference through the toggle

This means:
- first-time users follow the system
- users who explicitly choose dark keep dark after refresh
- users who explicitly choose light keep light after refresh

## Toggle Behavior

Keep the current header button and its compact interaction model.

Behavior:
- if the resolved theme is currently `light`, clicking the button sets explicit `dark`
- if the resolved theme is currently `dark`, clicking the button sets explicit `light`

This is intentionally simple:
- the default state still follows system
- once the user manually toggles, they have declared a preference override
- no extra UI is required for this task

This design does not add an explicit `Auto` toggle target yet. Returning to follow-system mode can be added later if needed.

## System Theme Changes

When `themePreference === 'auto'`:
- subscribe to `window.matchMedia('(prefers-color-scheme: dark)')`
- update `resolvedTheme` when the OS theme changes

When `themePreference !== 'auto'`:
- ignore system theme changes

This preserves the expected meaning of follow-system mode without affecting explicit user overrides.

## Component Boundaries

Expected frontend changes:
- `web/src/App.tsx`
  - replace the current single `theme` state with preference + resolved theme handling
  - persist theme preference
  - react to system theme changes while in `auto`
- `web/src/theme.ts`
  - add small helpers for loading, saving, and resolving theme preference

No CSS redesign is required. Existing `[data-theme='dark']` styling remains the source of visual behavior.

## Verification

Manual verification:
1. clear saved theme preference and refresh
2. confirm the UI follows the current system theme
3. click the theme toggle and refresh
4. confirm the explicit light/dark choice persists
5. clear saved preference again
6. while in default mode, switch the OS theme and confirm the UI follows it

Frontend verification:
- `cd web; npm run lint`
- `cd web; npm run build`

## Approval State
This design reflects the user-approved direction on 2026-04-10:
- default behavior should follow the system theme
- explicit dark/light choices should persist after refresh
- the next step should be writing the spec before implementation
