# ADR 004: Activepieces Before n8n

## Status

Accepted

## Context

Stage-based automation (Telegram join → CRM update → Plane task → admin alert) needs a no-code bridge. The stack lists both Activepieces and optional n8n. Installing two workflow engines increases ops burden and splits failure debugging.

The case study maps "Stage-based automation" to Activepieces first; n8n is "advanced workflow only if needed."

## Decision

Use **Activepieces** as the first automation bridge for MVP flows documented in `config/activepieces-flows-spec.md`.

**Do not install n8n in MVP** unless explicitly requested. `N8N_API_URL` and `N8N_API_KEY` remain optional in `.env.example` for future use.

All flows must log failures to `activity_logs`. Activepieces is a bridge, not source of truth.

## Consequences

### Positive

- One automation platform to learn and monitor
- Open-source, self-hostable
- Clear spec-driven rollout in Phase 7

### Negative

- Complex branching may eventually require n8n or code
- Webhook reliability depends on VPS/network health

## Alternatives Considered

- **n8n first** — rejected for MVP (heavier default install)
- **Zapier** — rejected (not open-source, case study uses OSS pattern)
