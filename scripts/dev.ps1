$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

python -m uvicorn agentops_api.main:app --reload --host 127.0.0.1 --port 8000
