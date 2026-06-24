# ADR 005: One Hermes Instance, Five Skills

## Status

Accepted

## Context

The legacy `CLAUDE.md` rule is explicit: **1 Hermes instance = 5 skill files**. Prior attempts to spin up multiple Hermes agents or an "Agent 6" increased coordination cost and broke the operating rhythm model.

Agent 5 (monitor) is a **skill file**, not a separate Hermes deployment.

## Decision

Maintain **one Hermes instance** with exactly five skill YAML files:

| Skill | File | Role |
| ----- | ---- | ---- |
| Agent 1 | `skills/agent1-capture.yaml` | Capture / Telegram attribution |
| Agent 2 | `skills/agent2-onboard.yaml` | Onboarding D1–D7 |
| Agent 3 | `skills/agent3-daily-loop.yaml` | Daily loop, Apify, reports |
| Agent 4 | `skills/agent4-twenty-crm-sync.yaml` | Twenty CRM sync |
| Agent 5 | `skills/agent5-monitor.yaml` | Health, founder report, rhythm |

Do **not** create five Hermes instances. Do **not** create Agent 6.

Legacy `skills/agent4-crm-sync.yaml` (EspoCRM) is retained for reference only with a LEGACY note.

## Consequences

### Positive

- Single webhook/runtime to secure and monitor
- Clear skill boundaries map to case study modules
- Agent 5 provides unified operating rhythm

### Negative

- All skills share one runtime failure domain (mitigated by health checks)
- Skill YAML must stay disciplined to avoid monolith prompts

## Alternatives Considered

- **Five Hermes instances** — rejected (legacy anti-pattern)
- **Agent 6 for automation** — rejected (Activepieces + skills cover scope)
