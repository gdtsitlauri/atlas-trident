from pathlib import Path

from atlas.orchestrator import AtlasOrchestrator


def test_orchestrator_runs_end_to_end_cycle(tmp_path) -> None:
    logs_dir = tmp_path / "logs"
    orchestrator = AtlasOrchestrator(config_path="config/default.toml", logs_dir=str(logs_dir))

    schedule = {
        1: [{"type": "overload", "service_id": "svc-1", "factor": 1.8}],
        2: [{"type": "latency_spike", "node_id": "node-2", "extra_ms": 120}],
    }

    reports = orchestrator.run(steps=3, event_schedule=schedule)
    assert len(reports) == 3
    assert any(report.proposals >= 0 for report in reports)

    metrics_file = Path(logs_dir) / "metrics.csv"
    state_file = Path(logs_dir) / "state_latest.json"
    db_file = Path(logs_dir) / "atlas_ledger.db"
    metadata_file = Path(logs_dir) / "run_metadata.json"
    snapshot_file = Path(logs_dir) / "config_snapshot.json"
    summary_file = Path(logs_dir) / "summary.json"
    cycle_reports_file = Path(logs_dir) / "cycle_reports.json"

    assert metrics_file.exists()
    assert state_file.exists()
    assert db_file.exists()
    assert metadata_file.exists()
    assert snapshot_file.exists()
    assert summary_file.exists()
    assert cycle_reports_file.exists()

    decisions = orchestrator.ledger.list_recent("decisions", limit=10)
    assert decisions
