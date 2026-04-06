param(
    [string]$PythonExe = "python"
)

$ErrorActionPreference = "Stop"

& $PythonExe -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt
& .\.venv\Scripts\python.exe -m pip install -e .

Write-Host "ATLAS setup complete."
