# Benchmarking Guide

ATLAS benchmark suite compares policy baselines over shared scenarios and writes machine-readable outputs.

## Supported Baselines

- random_policy
- rule_based_policy
- trident_no_rl
- trident_no_trust
- full_trident

## Supported Scenarios

- overload
- node_failure
- latency_spike
- conflicting_proposals
- resource_scarcity

## Command

```bash
python experiments/run_benchmark.py --steps 20 --scenarios overload,node_failure,latency_spike,conflicting_proposals,resource_scarcity --baselines random_policy,rule_based_policy,trident_no_rl,trident_no_trust,full_trident --seeds 42 --results-root results
```

## Output Layout

```text
results/
  benchmark_runs/
    benchmark_<timestamp>/
      <baseline>/<scenario>/seed_<seed>/
        summary.json
        cycle_reports.json
        metrics.csv
        run_metadata.json
        config_snapshot.json
        ...
  summaries/
    benchmark_<timestamp>.csv
    benchmark_<timestamp>.json
    benchmark_<timestamp>_metadata.json
  sample_reports/
    benchmark_<timestamp>_sample.json
```

## Comparable Metrics

- decision_latency_ms_avg
- consensus_latency_ms_avg
- sla_violations_total
- recovery_time_ms_max
- resource_utilization_avg
- cost_proxy_avg
- action_success_rate
- governance_overhead_total
- total_proposals
- total_approved
- latest_utility

## Reproducibility

Each run includes:
- seed
- deterministic mode flag
- baseline mode
- config snapshot
- per-run metadata JSON
