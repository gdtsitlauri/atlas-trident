param(
    [ValidateSet("overload", "node_failure", "latency_spike", "conflicting_proposals", "resource_scarcity")]
    [string]$Scenario = "overload",
    [int]$Steps = 20,
    [ValidateSet("random_policy", "rule_based_policy", "trident_no_rl", "trident_no_trust", "full_trident")]
    [string]$BaselineMode = "full_trident",
    [int]$Seed = 42,
    [bool]$Deterministic = $true,
    [string]$Config = "config/default.toml",
    [string]$LogsDir = "logs/latest"
)

$ErrorActionPreference = "Stop"

& .\.venv\Scripts\python.exe experiments/run_scenario.py --scenario $Scenario --steps $Steps --baseline-mode $BaselineMode --seed $Seed --deterministic:$Deterministic --config $Config --logs-dir $LogsDir
