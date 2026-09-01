# SitRep n8n Integration Contract

SitRep keeps deterministic fusion, mission-pack selection, COA scoring, policy checks, persistence, and human authorization in the API. n8n is used for orchestration, enrichment, notifications, and external-system integrations.

## Recommended flow

1. External source -> n8n trigger/poll/webhook.
2. n8n normalizes the source payload.
3. n8n POSTs the normalized observation to `/api/v1/observations/`.
4. SitRep performs entity association, fusion, provenance, decision-trigger evaluation, mission-pack selection, and—when warranted—creates a proposed decision.
5. n8n inspects `decision_trigger.should_trigger` and `decision_proposal` in the response.
6. If a proposal exists, n8n may enrich context from approved external sources and notify authorized users/systems.
7. Human reviewers retrieve `/decisions/{decision_id}` and `/decisions/{decision_id}/explanation`.
8. Authorized users call `/decisions/{decision_id}/approve` or `/reject`.
9. Only approved downstream workflows may execute permitted operational integrations.

## Observation response fields used by n8n

```json
{
  "decision_trigger": {
    "should_trigger": true,
    "severity": "high",
    "reasons": ["..."],
    "human_authorization_required": true,
    "next_step": "generate_course_of_action"
  },
  "decision_proposal": {
    "decision_id": "...",
    "mission_pack": "wildfire-emergency",
    "status": "proposed",
    "recommended_option": "Pre-stage response resources",
    "requires_human_authorization": true
  }
}
```

## Guardrails

- n8n must not bypass SitRep's decision approval state.
- Consequential actions remain disabled until explicit authorization is recorded.
- Integrations should preserve tenant, mission, classification, source, and provenance metadata.
- Secrets belong in n8n/Railway credential stores, never in workflow JSON committed to GitHub.
- Defence/classified deployments should support private or sovereign n8n instances rather than third-party SaaS execution.

## Initial integrations to build

- Environment/weather and wildfire enrichment.
- Maritime/AIS and vessel-data enrichment.
- Email/Slack/Teams notification adapters.
- Webhook adapter for Base44 UI refresh.
- Later: Redis-backed event queue for burst ingestion and disconnected/edge synchronization.
