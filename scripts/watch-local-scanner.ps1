param(
  [int]$Port = 8001,
  [string]$SchedulerMode = "burst",
  [int]$SchedulerBatchSize = 20,
  [int]$CheckIntervalSeconds = 60
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$WatchdogLog = Join-Path $LogsDir "local-scanner-watchdog.log"
$BackendScript = Join-Path $PSScriptRoot "start-local-backend.ps1"
$BackendOut = Join-Path $LogsDir "local-backend.out.log"
$BackendErr = Join-Path $LogsDir "local-backend.err.log"

function Write-ScannerLog([string]$Message) {
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Encoding ASCII -Path $WatchdogLog -Value "[$stamp] $Message"
}

function Test-BackendHealth {
  try {
    Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/stats/health" -TimeoutSec 10 | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Start-Backend {
  Write-ScannerLog "Starting local backend on port $Port with scheduler mode=$SchedulerMode batch=$SchedulerBatchSize"
  $backendArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$BackendScript`"",
    "-Port", "$Port",
    "-SchedulerMode", "$SchedulerMode",
    "-SchedulerBatchSize", "$SchedulerBatchSize"
  )

  $backend = Start-Process -FilePath powershell.exe `
    -ArgumentList $backendArgs `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $BackendOut `
    -RedirectStandardError $BackendErr `
    -PassThru
  Write-ScannerLog "Started backend wrapper PID $($backend.Id)"
}

function Ensure-Backend {
  if (Test-BackendHealth) {
    return
  }

  $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($listener) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
    $cmd = if ($proc) { $proc.CommandLine } else { "" }
    if ($cmd -and ($cmd -like "*uvicorn*" -or $cmd -like "*start-local-backend.ps1*")) {
      Write-ScannerLog "Stopping unhealthy backend PID $($listener.OwningProcess)"
      Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
      Start-Sleep -Seconds 2
    } else {
      Write-ScannerLog "Port $Port is occupied by a non-backend process; leaving it alone. CommandLine=$cmd"
      return
    }
  }

  Start-Backend
  for ($i = 1; $i -le 30; $i++) {
    if (Test-BackendHealth) {
      Write-ScannerLog "Backend health check passed"
      return
    }
    Start-Sleep -Seconds 2
  }
  Write-ScannerLog "Backend did not become healthy after start; will retry"
}

function Ensure-Scheduler {
  try {
    $body = @{
      mode = $SchedulerMode
      batch_size = $SchedulerBatchSize
    } | ConvertTo-Json
    $status = Invoke-RestMethod `
      -Uri "http://127.0.0.1:$Port/api/scheduler/start" `
      -Method POST `
      -ContentType "application/json" `
      -Body $body `
      -TimeoutSec 15
    Write-ScannerLog "Scheduler status=$($status.status) running=$($status.running) paused=$($status.paused) mode=$($status.mode) batch=$($status.batch_size)"
  } catch {
    Write-ScannerLog "Scheduler ensure failed: $($_.Exception.Message)"
  }
}

Write-ScannerLog "Local scanner watchdog started"
while ($true) {
  try {
    Ensure-Backend
    if (Test-BackendHealth) {
      Ensure-Scheduler
    }
  } catch {
    Write-ScannerLog "Watchdog loop error: $($_.Exception.Message)"
  }
  Start-Sleep -Seconds ([Math]::Max(15, $CheckIntervalSeconds))
}
