param(
    [switch]$Execute,
    [string]$DbPath = ".agentops/agentops.db",
    [string]$RetentionDays = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$Arguments = @("-m", "agentops_api.retention", "--db-path", $DbPath)
if ($Execute) {
    $Arguments += "--execute"
}
if ($RetentionDays) {
    $Arguments += @("--retention-days", $RetentionDays)
}

python @Arguments
