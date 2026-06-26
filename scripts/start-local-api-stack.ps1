param(
  [int]$Port = 8000,
  [switch]$NoScheduler,
  [switch]$StartQuickTunnel
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$BackendScript = Join-Path $PSScriptRoot "start-local-backend.ps1"
$BackendArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-File", "`"$BackendScript`"",
  "-Port", "$Port"
)
if ($NoScheduler) {
  $BackendArgs += "-NoScheduler"
}

$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $existing) {
  $backend = Start-Process -FilePath powershell.exe `
    -ArgumentList $BackendArgs `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogsDir "local-backend.out.log") `
    -RedirectStandardError (Join-Path $LogsDir "local-backend.err.log") `
    -PassThru
  Write-Host "Started local backend PID $($backend.Id)"
} else {
  Write-Host "Backend already listening on port $Port"
}

for ($i = 1; $i -le 30; $i++) {
  try {
    $health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/api/stats" -TimeoutSec 5
    Write-Host "Backend ready: $($health.StatusCode)"
    break
  } catch {
    if ($i -eq 30) {
      throw "Backend did not become ready on port $Port. Check logs/local-backend.err.log."
    }
    Start-Sleep -Seconds 2
  }
}

if ($StartQuickTunnel) {
  $TunnelScript = Join-Path $PSScriptRoot "start-cloudflare-quick-tunnel.ps1"
  $TunnelArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$TunnelScript`"",
    "-LocalUrl", "http://127.0.0.1:$Port"
  )
  $tunnel = Start-Process -FilePath powershell.exe `
    -ArgumentList $TunnelArgs `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogsDir "cloudflared-quick-tunnel.out.log") `
    -RedirectStandardError (Join-Path $LogsDir "cloudflared-quick-tunnel.err.log") `
    -PassThru
  Write-Host "Started Cloudflare quick tunnel PID $($tunnel.Id)"
  Write-Host "Check logs/cloudflared-quick-tunnel.log for the temporary public URL."
}
