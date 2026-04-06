from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from atlas.orchestrator import AtlasOrchestrator

LOGGER = logging.getLogger(__name__)

CONFIG_PATH = os.getenv("ATLAS_CONFIG", "config/default.toml")
LOGS_DIR = os.getenv("ATLAS_LOGS_DIR")
BASELINE_MODE = os.getenv("ATLAS_BASELINE_MODE")
SEED_VALUE = int(os.getenv("ATLAS_SEED")) if os.getenv("ATLAS_SEED") else None


def _parse_optional_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


DETERMINISTIC_MODE = _parse_optional_bool(os.getenv("ATLAS_DETERMINISTIC"))


class CycleRequest(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)


class RunRequest(BaseModel):
    steps: int = Field(default=10, ge=1, le=500)
    event_schedule: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)


def create_app(config_path: str | None = None, logs_dir: str | None = None) -> FastAPI:
    orchestrator = AtlasOrchestrator(
        config_path=config_path or CONFIG_PATH,
        logs_dir=logs_dir or LOGS_DIR,
        baseline_mode=BASELINE_MODE,
        seed=SEED_VALUE,
        deterministic_mode=DETERMINISTIC_MODE,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        LOGGER.info("ATLAS API startup baseline=%s", orchestrator.config.baseline_mode)
        yield
        LOGGER.info("ATLAS API shutdown")

    app = FastAPI(
        title="ATLAS API",
        version="0.2.0",
        description="Control-plane API for ATLAS TRIDENT prototype",
        lifespan=lifespan,
    )
    app.state.orchestrator = orchestrator

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "baseline_mode": orchestrator.config.baseline_mode,
            "seed": orchestrator.config.seed,
        }

    @app.get("/ready")
    def ready() -> dict[str, Any]:
        audit = orchestrator.ledger.audit_consistency()
        return {"status": "ready", "governance_ok": audit["ok"]}

    @app.get("/state")
    def state() -> dict[str, Any]:
        return orchestrator.get_state()

    @app.get("/trust")
    def trust() -> dict[str, float]:
        return orchestrator.ledger.get_all_trust()

    @app.post("/cycle")
    def cycle(request: CycleRequest) -> dict[str, Any]:
        try:
            report = orchestrator.run_cycle(external_events=request.events)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Cycle execution failed")
            raise HTTPException(status_code=500, detail=f"cycle_failed: {exc}") from exc
        return report.model_dump()

    @app.post("/run")
    def run(request: RunRequest) -> list[dict[str, Any]]:
        try:
            normalized_schedule: dict[int, list[dict[str, Any]]] = {
                int(step): events for step, events in request.event_schedule.items()
            }
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"invalid_event_schedule: {exc}") from exc

        try:
            reports = orchestrator.run(steps=request.steps, event_schedule=normalized_schedule)
        except Exception as exc:  # noqa: BLE001
            LOGGER.exception("Run execution failed")
            raise HTTPException(status_code=500, detail=f"run_failed: {exc}") from exc
        return [report.model_dump() for report in reports]

    @app.get("/ledger/{table}")
    def ledger_table(table: str, limit: int = 30) -> list[dict[str, Any]]:
        try:
            return orchestrator.ledger.list_recent(table, limit=limit)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/governance/audit")
    def governance_audit() -> dict[str, Any]:
        return orchestrator.ledger.audit_consistency()

    @app.get("/metrics/latest")
    def latest_metrics() -> dict[str, Any]:
        metrics_path = Path(orchestrator.config.paths.logs_dir) / "metrics.csv"
        if not metrics_path.exists():
            return {"message": "no_metrics_available"}
        lines = metrics_path.read_text(encoding="utf-8").strip().splitlines()
        if len(lines) <= 1:
            return {"message": "no_metric_rows"}
        header = lines[0].split(",")
        values = lines[-1].split(",")
        return dict(zip(header, values, strict=False))

    @app.get("/run-metadata")
    def run_metadata() -> dict[str, Any]:
        metadata_path = Path(orchestrator.config.paths.logs_dir) / "run_metadata.json"
        if not metadata_path.exists():
            return {"message": "run_metadata_not_found"}
        return json.loads(metadata_path.read_text(encoding="utf-8"))

    return app


app = create_app(CONFIG_PATH, LOGS_DIR)
