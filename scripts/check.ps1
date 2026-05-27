$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

& "$PSScriptRoot\lint.ps1"
& "$PSScriptRoot\test.ps1"
python harness/validate.py
