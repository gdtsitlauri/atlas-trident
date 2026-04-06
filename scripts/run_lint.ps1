$ErrorActionPreference = "Stop"

& .\.venv\Scripts\python.exe -m ruff check src tests experiments dashboard
