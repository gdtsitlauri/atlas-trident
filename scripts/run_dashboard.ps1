param(
    [int]$Port = 8501,
    [string]$LogsDir = "logs/latest"
)

$ErrorActionPreference = "Stop"
$env:ATLAS_LOGS_DIR = $LogsDir

& .\.venv\Scripts\streamlit.exe run dashboard/app.py --server.port $Port --server.address 0.0.0.0
