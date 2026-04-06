param(
    [int]$Steps = 20,
    [string]$Scenarios = "overload,node_failure,latency_spike,conflicting_proposals,resource_scarcity",
    [string]$Baselines = "random_policy,rule_based_policy,trident_no_rl,trident_no_trust,full_trident",
    [string]$Seeds = "42",
    [bool]$Deterministic = $true,
    [string]$Config = "config/default.toml",
    [string]$ResultsRoot = "results"
)

$ErrorActionPreference = "Stop"

& .\.venv\Scripts\python.exe experiments/run_benchmark.py --steps $Steps --scenarios $Scenarios --baselines $Baselines --seeds $Seeds --deterministic:$Deterministic --config $Config --results-root $ResultsRoot
