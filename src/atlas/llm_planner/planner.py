from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod

import requests
from pydantic import ValidationError

from atlas.config import AtlasConfig
from atlas.types import AllowedAction, CandidateAction, CandidatePlan, TwinSnapshot

LOGGER = logging.getLogger(__name__)


class PlannerValidationError(ValueError):
    """Raised when planner payload does not satisfy strict action schema."""


def _dedupe_candidates(candidates: list[CandidateAction]) -> list[CandidateAction]:
    seen: set[str] = set()
    unique: list[CandidateAction] = []
    for candidate in candidates:
        key = json.dumps(candidate.model_dump(), sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def validate_candidate_payload(payload: dict | list, max_candidates: int) -> list[CandidateAction]:
    normalized_payload = payload
    if isinstance(payload, list):
        normalized_payload = {"candidates": payload}
    if not isinstance(normalized_payload, dict):
        raise PlannerValidationError("invalid_payload_type")

    try:
        plan = CandidatePlan.model_validate(normalized_payload)
    except ValidationError as exc:
        raise PlannerValidationError("invalid_llm_candidate_schema") from exc

    unique = _dedupe_candidates(plan.candidates)
    if not unique:
        raise PlannerValidationError("empty_candidate_list")
    return unique[:max(1, max_candidates)]


class BasePlanner(ABC):
    @abstractmethod
    def plan(self, snapshot: TwinSnapshot, max_candidates: int = 5) -> list[CandidateAction]:
        raise NotImplementedError


class MockPlanner(BasePlanner):
    """Heuristic planner used by default for reproducibility and low resource usage."""

    def plan(self, snapshot: TwinSnapshot, max_candidates: int = 5) -> list[CandidateAction]:
        services = snapshot.services
        metrics = snapshot.metrics
        sorted_by_latency = sorted(
            services.items(), key=lambda item: float(item[1].get("latency_ms", 0.0)), reverse=True
        )
        hottest_service = sorted_by_latency[0][0] if sorted_by_latency else "svc-1"
        coolest_service = sorted_by_latency[-1][0] if sorted_by_latency else "svc-1"

        candidates: list[CandidateAction] = []

        if metrics.sla_violations > 0:
            candidates.append(
                CandidateAction(action=AllowedAction.SCALE_UP_SERVICE, target_service=hottest_service)
            )
            candidates.append(CandidateAction(action=AllowedAction.REBALANCE_RESOURCES))

        if metrics.resource_utilization > 0.88:
            candidates.append(
                CandidateAction(
                    action=AllowedAction.RATE_LIMIT_SERVICE,
                    target_service=hottest_service,
                    params={"factor": 0.85},
                )
            )
            candidates.append(
                CandidateAction(action=AllowedAction.MIGRATE_WORKLOAD, target_service=hottest_service)
            )

        if metrics.resource_utilization < 0.35:
            candidates.append(
                CandidateAction(action=AllowedAction.SCALE_DOWN_SERVICE, target_service=coolest_service)
            )

        if any(not bool(node.get("healthy", True)) for node in snapshot.nodes.values()):
            impacted_services = [
                svc_id
                for svc_id, svc in services.items()
                if not snapshot.nodes.get(str(svc.get("node_id", "")), {}).get("healthy", True)
            ]
            for svc_id in impacted_services:
                candidates.append(
                    CandidateAction(action=AllowedAction.FAILOVER_TO_REPLICA, target_service=svc_id)
                )

        candidates.append(CandidateAction(action=AllowedAction.DEFER_LOW_PRIORITY_JOBS, params={"factor": 0.80}))
        candidates.append(CandidateAction(action=AllowedAction.RESTART_SERVICE, target_service=hottest_service))

        unique = _dedupe_candidates(candidates)
        if not unique:
            unique = [CandidateAction(action=AllowedAction.REBALANCE_RESOURCES)]

        return unique[:max(1, max_candidates)]


class HTTPPlannerBase(MockPlanner):
    def __init__(self, config: AtlasConfig) -> None:
        self.config = config

    def _build_prompt(self, snapshot: TwinSnapshot, max_candidates: int) -> str:
        allowed = [action.value for action in AllowedAction]
        payload = {
            "step": snapshot.step,
            "metrics": snapshot.metrics.model_dump(),
            "nodes": snapshot.nodes,
            "services": snapshot.services,
        }
        schema = {
            "candidates": [
                {
                    "action": "one of allowed actions",
                    "target_service": "optional service id",
                    "target_node": "optional node id",
                    "params": {},
                }
            ]
        }
        return (
            "You are planning constrained infrastructure actions. "
            "Return JSON only and no prose. "
            f"Allowed actions: {allowed}. "
            f"Return at most {max_candidates} candidates. "
            f"Schema: {json.dumps(schema)}. "
            f"State: {json.dumps(payload)}"
        )

    def _extract_json(self, raw: str) -> dict:
        raw = raw.strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise ValueError("no_json_payload_found")
        return json.loads(raw[start : end + 1])

    def _validate_candidates(self, payload: dict, max_candidates: int) -> list[CandidateAction]:
        return validate_candidate_payload(payload, max_candidates=max_candidates)


class OllamaPlanner(HTTPPlannerBase):
    def plan(self, snapshot: TwinSnapshot, max_candidates: int = 5) -> list[CandidateAction]:
        prompt = self._build_prompt(snapshot, max_candidates)
        url = os.getenv("ATLAS_OLLAMA_URL", self.config.llm.ollama_url)
        model = os.getenv("ATLAS_OLLAMA_MODEL", self.config.llm.ollama_model)

        try:
            response = requests.post(
                url,
                json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
                timeout=self.config.llm.request_timeout_sec,
            )
            response.raise_for_status()
            raw = response.json().get("response", "")
            payload = self._extract_json(raw)
            return self._validate_candidates(payload, max_candidates)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Ollama planner fallback to mock planner: %s", exc)
            return super().plan(snapshot, max_candidates)


class OpenAICompatiblePlanner(HTTPPlannerBase):
    def plan(self, snapshot: TwinSnapshot, max_candidates: int = 5) -> list[CandidateAction]:
        prompt = self._build_prompt(snapshot, max_candidates)
        url = os.getenv("ATLAS_OPENAI_URL", self.config.llm.openai_url)
        model = os.getenv("ATLAS_OPENAI_MODEL", self.config.llm.openai_model)
        api_key = os.getenv("ATLAS_OPENAI_API_KEY", "")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }

        try:
            response = requests.post(url, headers=headers, json=body, timeout=self.config.llm.request_timeout_sec)
            response.raise_for_status()
            raw = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            payload = self._extract_json(raw)
            return self._validate_candidates(payload, max_candidates)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("OpenAI-compatible planner fallback to mock planner: %s", exc)
            return super().plan(snapshot, max_candidates)


def build_planner(mode: str, config: AtlasConfig) -> BasePlanner:
    normalized = (mode or "mock").strip().lower()
    if normalized == "ollama":
        return OllamaPlanner(config)
    if normalized in {"openai", "openai_compatible", "remote"}:
        return OpenAICompatiblePlanner(config)
    return MockPlanner()
