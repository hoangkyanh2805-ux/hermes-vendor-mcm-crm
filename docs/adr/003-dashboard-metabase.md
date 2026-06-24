# ADR 003: Metabase for Founder Dashboard

## Status

Accepted

## Context

Founders need executive KPI visibility: growth, country/vendor performance, CRM funnel, purgatory alerts, and system health. Building a custom dashboard first would delay MVP and duplicate SQL already expressible as views.

The case study maps "Executive/founder dashboards" to a BI layer, not an application frontend.

## Decision

Use **Metabase** connected to Supabase/Postgres for the founder dashboard. Define cards and layout in `config/metabase-dashboard-spec.md`; implement queries via `db/views.sql`.

Do not build a custom React/Next dashboard for MVP. Do not use Google Sheets or Superset as the primary dashboard.

## Consequences

### Positive

- Fast time-to-dashboard using SQL views
- Non-engineers can adjust cards in Metabase UI
- Single query layer shared with Agent 5 reports

### Negative

- Metabase instance must be hosted and secured
- Some purgatory alerts may later need Activepieces for push notifications

## Alternatives Considered

- **Custom dashboard app** — deferred post-MVP
- **Superset** — rejected (explicitly out of MVP stack)
- **Google Sheet charts** — rejected (not source of truth)
