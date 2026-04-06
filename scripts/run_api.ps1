param(
    [string]$Host = "0.0.0.0",
    [int]$Port = 8000,
    [string]$Config = "config/default.toml",
    [ValidateSet("random_policy", "rule_based_policy", "trident_no_rl", "trident_no_trust", "full_trident")]
    [string]$BaselineMode = "full_trident",
    [int]$Seed = 42,
    [bool]$Deterministic = $true,
    [string]$LogsDir = "logs/latest"
)

$ErrorActionPreference = "Stop"
$env:ATLAS_CONFIG = $Config
$env:ATLAS_BASELINE_MODE = $BaselineMode
$env:ATLAS_SEED = "$Seed"
$env:ATLAS_DETERMINISTIC = "$Deterministic"
$env:ATLAS_LOGS_DIR = $LogsDir

& .\.venv\Scripts\uvicorn.exe atlas.api.main:app --host $Host --port $Port
