# ATLAS API Reference

Implementation:
- src/atlas/api/main.py

## Runtime Notes

- API owns an orchestrator instance.
- Baseline mode, seed, and deterministic behavior can be controlled via environment variables:
  - ATLAS_BASELINE_MODE
  - ATLAS_SEED
  - ATLAS_DETERMINISTIC
- Config and logs location:
  - ATLAS_CONFIG
  - ATLAS_LOGS_DIR

## Endpoints

### GET /health
Returns service heartbeat and runtime context.

Response example:
```json
{
  "status": "ok",
  "baseline_mode": "full_trident",
  "seed": 42
}
```

### GET /ready
Returns readiness and governance consistency state.

### GET /state
Returns current simulator state and orchestrator context.

### GET /trust
Returns all trust scores.

### POST /cycle
Runs one autonomous cycle.

Request:
```json
{
  "events": [
    {"type": "overload", "service_id": "svc-1", "factor": 1.8}
  ]
}
```

### POST /run
Runs multiple cycles.

Request:
```json
{
  "steps": 10,
  "event_schedule": {
    "2": [{"type": "latency_spike", "node_id": "node-2", "extra_ms": 120}],
    "4": [{"type": "node_failure", "node_id": "node-1", "duration": 3}]
  }
}
```

### GET /ledger/{table}?limit=30
Tables:
- blocks
- proposals
- votes
- decisions
- executions
- trust_scores

### GET /governance/audit
Returns consistency checks for proposal-vote-decision-execution linkage and block hash chain integrity.

### GET /metrics/latest
Returns latest metrics.csv row from current logs directory.

### GET /run-metadata
Returns run_metadata.json for the active run.

## Error Behavior

- Invalid ledger table name returns HTTP 400.
- Invalid event schedule payload returns HTTP 400.
- Runtime cycle or run execution failures return HTTP 500 with descriptive detail.
