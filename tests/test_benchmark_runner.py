from pathlib import Path

from atlas.benchmarking import run_benchmark_suite


def test_benchmark_runner_generates_outputs(tmp_path) -> None:
    result = run_benchmark_suite(
        config_path="config/default.toml",
        steps=2,
        scenarios=["overload"],
        baseline_modes=["random_policy", "full_trident"],
        seeds=[11],
        results_root=str(tmp_path / "results"),
        deterministic_mode=True,
    )

    assert result["records"] == 2
    assert Path(result["summary_csv"]).exists()
    assert Path(result["summary_json"]).exists()
    assert Path(result["metadata_json"]).exists()
    assert Path(result["sample_report"]).exists()
