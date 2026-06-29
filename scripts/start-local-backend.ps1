param(
  [int]$Port = 8001,
  [switch]$NoScheduler,
  [int]$SchedulerBatchSize = 20,
  [string]$SchedulerMode = "burst"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BackendDir = Join-Path $RepoRoot "backend"
$Python = (Get-Command python -ErrorAction Stop).Source

$env:BACKEND_DIR = $BackendDir
$env:AUTO_START_SCHEDULER = if ($NoScheduler) { "0" } else { "1" }
$env:SCHEDULER_MODE = $SchedulerMode
$env:SCHEDULER_BATCH_SIZE = [string]$SchedulerBatchSize

Set-Location $BackendDir
Write-Host "Starting Niche Research backend on http://127.0.0.1:$Port"
Write-Host "Scheduler: $($env:AUTO_START_SCHEDULER) mode=$SchedulerMode batch=$SchedulerBatchSize"
& $Python -m uvicorn main:app --host 127.0.0.1 --port $Port
