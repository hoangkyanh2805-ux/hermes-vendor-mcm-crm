# ADR 002: Twenty CRM Over EspoCRM

## Status

Accepted

## Context

The legacy stack integrated EspoCRM for lead pipeline management. EspoCRM added operational overhead, did not align with the case-study CRM pattern, and is not the target for new XAUUSD growth workflows.

Twenty CRM provides a modern pipeline UI with API access and fits the "CRM pipeline and stage velocity" module in the case study mapping.

## Decision

Use **Twenty CRM** for the new Hermes XAUUSD pipeline. **Supabase remains source of truth**; Twenty receives sync from `scripts/sync_to_twenty.py` and `skills/agent4-twenty-crm-sync.yaml`.

**EspoCRM is legacy reference only.** Do not extend `skills/agent4-crm-sync.yaml` or add new EspoCRM integrations.

## Consequences

### Positive

- Cleaner pipeline aligned to seeded stages in Postgres
- API-friendly sync from Supabase events
- Founder visibility without custom CRM UI

### Negative

- Migration period where EspoCRM data may exist in parallel
- Twenty API configuration required per environment

## Alternatives Considered

- **Continue EspoCRM** — rejected (legacy, not case-study aligned)
- **SuiteCRM / custom CRM** — rejected for MVP scope
