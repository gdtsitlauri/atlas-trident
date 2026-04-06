param(
    [int]$Steps = 20,
    [ValidateSet("random_policy", "rule_based_policy", "trident_no_rl", "trident_no_trust", "full_trident")]
    [string]$BaselineMode = "full_trident",
    [int]$Seed = 42,
    [bool]$Deterministic = $true,
    [string]$Config = "config/default.toml",
    [string]$LogsDir = "logs/latest"
)

$ErrorActionPreference = "Stop"

& .\.venv\Scripts\python.exe -m atlas.cli run --steps $Steps --baseline-mode $BaselineMode --seed $Seed --deterministic:$Deterministic --config $Config --logs-dir $LogsDir
