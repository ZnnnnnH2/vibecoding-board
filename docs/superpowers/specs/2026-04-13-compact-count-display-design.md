# Compact Count Display Design

## Summary

This change standardizes large count displays in the admin UI by introducing one shared formatter for count-like values. Request counts, token totals, and chart totals should render in compact `K / M / B` form, while precision-sensitive values such as latency, percentages, priorities, and HTTP status codes remain unchanged.

## Goals

- Improve visual scanability of large count values across the admin UI.
- Reuse one shared formatting helper instead of repeating compact-number logic in components.
- Keep precision-sensitive fields exact.

## Non-Goals

- No backend changes.
- No API or data-model changes.
- No localization-specific compact units such as `万` or `亿`.
- No changes to sorting, aggregation, or persistence behavior.

## Formatter Design

Add a shared helper in `web/src/format.ts`:

- Name: `formatCountCompact`
- Input: `number | null | undefined`
- Output:
  - `N/A` or a caller-provided fallback for missing values
  - raw rounded integer for values below `1000`
  - compact `K / M / B` output for larger values

The formatter is intentionally count-specific and must not replace the existing generic numeric formatter used by latency displays.

## UI Scope

Apply the compact count formatter to these count-focused displays:

- Overview KPI cards for provider count and served request count
- Overview runtime card for usage row count
- All-time token usage KPI cards and provider/model breakdown tables
- Provider list request totals
- Overview health snapshot request totals
- Traffic detail token usage fields
- Metrics chart latest values for request and token trends
- Metrics distribution totals and item labels

Keep these displays unchanged:

- Latency or duration values in `ms`
- Percentages
- Priorities
- HTTP status codes
- Timestamps
- Retry attempt ordinals

## Component Integration

### Shared Formatting

`web/src/format.ts` remains the single source for display formatting helpers. Count-aware components call `formatCountCompact` explicitly instead of relying on context-sensitive magic.

### Overview

`web/src/components/OverviewView.tsx` uses the compact formatter for count-focused KPI cards, token usage totals, token breakdown tables, runtime usage rows, health snapshot request totals, and count-oriented chart latest labels.

### Providers

`web/src/components/ProvidersView.tsx` formats the request total shown in each provider row without changing success rate or latency text.

### Traffic

`web/src/components/TrafficView.tsx` formats token usage triplets in expanded request details while leaving latency and HTTP metadata untouched.

### Metrics Charts

`web/src/components/MetricsCharts.tsx` formats request/token latest values and count-based chart totals. Duration trend labels remain on the existing numeric path.

## Error Handling

- Missing values continue to render a fallback string instead of crashing.
- Components that need localized fallback text can pass that string into the shared formatter.

## Testing And Verification

- Run `cd web && npm run lint`
- Run `cd web && npm run build`
- Confirm the generated admin bundle under `vibecoding_board/static/admin/` updates successfully
- Review the diff to ensure compact formatting only affects count-oriented displays
