from pathlib import Path

from fastapi.testclient import TestClient

from atlas.api.main import create_app


def test_api_health_cycle_and_audit(tmp_path) -> None:
    logs_dir = tmp_path / "api_logs"
    app = create_app(config_path="config/default.toml", logs_dir=str(logs_dir))

    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        ready = client.get("/ready")
        assert ready.status_code == 200

        cycle = client.post("/cycle", json={"events": []})
        assert cycle.status_code == 200
        assert "decision_latency_ms" in cycle.json()

        state = client.get("/state")
        assert state.status_code == 200
        assert "nodes" in state.json()

        audit = client.get("/governance/audit")
        assert audit.status_code == 200
        assert "ok" in audit.json()

        metadata = client.get("/run-metadata")
        assert metadata.status_code == 200
        assert "baseline_mode" in metadata.json()

    assert (Path(logs_dir) / "run_metadata.json").exists()
