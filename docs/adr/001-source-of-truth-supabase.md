# ADR 001: Supabase/Postgres as Source of Truth

## Status

Accepted

## Context

The legacy Hermes vendor stack used Google Sheets as the operational database for leads, members, and attribution. That approach caused sync drift, no transactional guarantees, limited query capability, and blocked reliable CRM/dashboard automation.

The ZeremAI case study pattern maps a unified lead/prospecting engine to a single relational source of truth.

## Decision

Use **Supabase/Postgres** as the single source of truth for:

- X account and campaign attribution
- Telegram joins and leads
- CRM stage events (Twenty syncs from here, not the reverse)
- Content performance, Apify intelligence, vendor tasks
- Activity logs and system health

Google Sheets may remain as an optional export/debug view only. It is not a write path for MVP.

## Consequences

### Positive

- One transactional store for all agents and automations
- SQL views power Metabase without custom app code
- `activity_logs` and triggers give auditability
- Twenty CRM, Plane, and Activepieces become downstream consumers

### Negative

- Requires Supabase project setup and migration discipline
- Team must stop extending Sheet-first workflows

## Alternatives Considered

- **Google Sheet as database** — rejected (legacy, drift-prone)
- **Twenty as source of truth** — rejected (CRM is pipeline visibility, not event store)
- **Dual-write Sheet + Supabase** — rejected for MVP (complexity without benefit)
