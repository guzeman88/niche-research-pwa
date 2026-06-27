param(
  [int]$Port = 8001,
  [string]$SiteId = "9c00efca-ced9-4097-b302-172437380b32",
  [Alias("RenderFallbackUrl")]
  [string]$BackupApiUrls = "",
  [ValidateSet("localtunnel", "cloudflare")]
  [string]$TunnelProvider = "localtunnel",
  [string]$LocalTunnelSubdomain = "etsy-niches-api-guzeman88",
  [switch]$NoDeploy
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
$SyncLog = Join-Path $LogsDir "local-api-netlify-sync.log"

trap {
  $message = "[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] ERROR: $($_.Exception.Message)"
  Add-Content -Encoding ASCII -Path $SyncLog -Value $message
  Write-Error $_
  exit 1
}

function Write-Step([string]$Message) {
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  $line = "[$stamp] $Message"
  Add-Content -Encoding ASCII -Path $SyncLog -Value $line
  Write-Host $line
}

function Wait-ForHttpOk([string]$Url, [int]$Attempts = 30, [int]$DelaySeconds = 2) {
  for ($i = 1; $i -le $Attempts; $i++) {
    try {
      $res = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 10
      if ($res.StatusCode -ge 200 -and $res.StatusCode -lt 300) {
        return $res
      }
    } catch {
      if ($i -eq $Attempts) {
        throw "Timed out waiting for $Url. Last error: $($_.Exception.Message)"
      }
      Start-Sleep -Seconds $DelaySeconds
    }
  }
}

function Get-QuickTunnelUrl([string]$OutPath, [string]$ErrPath) {
  foreach ($path in @($OutPath, $ErrPath)) {
    if (-not (Test-Path $path)) { continue }
    $text = Get-Content -Raw -Path $path -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($text)) { continue }
    $match = [regex]::Matches($text, "https://[-a-z0-9]+\.trycloudflare\.com") | Select-Object -Last 1
    if ($match) {
      return $match.Value
    }
  }
  return $null
}

function Get-LocalTunnelUrl([string]$OutPath, [string]$ErrPath) {
  foreach ($path in @($OutPath, $ErrPath)) {
    if (-not (Test-Path $path)) { continue }
    $text = Get-Content -Raw -Path $path -ErrorAction SilentlyContinue
    if ([string]::IsNullOrWhiteSpace($text)) { continue }
    $match = [regex]::Matches($text, "https://[-a-z0-9]+\.loca\.lt") | Select-Object -Last 1
    if ($match) {
      return $match.Value
    }
  }
  return $null
}

Write-Step "Ensuring local backend is running on http://127.0.0.1:$Port"
$BackendScript = Join-Path $PSScriptRoot "start-local-backend.ps1"
$existingBackend = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $existingBackend) {
  $backendArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$BackendScript`"",
    "-Port", "$Port"
  )
  $backend = Start-Process -FilePath powershell.exe `
    -ArgumentList $backendArgs `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput (Join-Path $LogsDir "local-backend.out.log") `
    -RedirectStandardError (Join-Path $LogsDir "local-backend.err.log") `
    -PassThru
  Write-Step "Started local backend PID $($backend.Id)"
} else {
  Write-Step "Backend already listening on port $Port"
}

Wait-ForHttpOk "http://127.0.0.1:$Port/api/stats/health" | Out-Null
Write-Step "Local backend health check passed"

$localUrl = "http://127.0.0.1:$Port"

$tunnelOut = Join-Path $LogsDir "cloudflared-local-api.out.log"
$tunnelErr = Join-Path $LogsDir "cloudflared-local-api.err.log"
Remove-Item -LiteralPath $tunnelOut, $tunnelErr -ErrorAction SilentlyContinue

function Start-VerifiedQuickTunnel {
  $Cloudflared = (Get-Command cloudflared -ErrorAction Stop).Source
  $oldTunnels = Get-CimInstance Win32_Process -Filter "name = 'cloudflared.exe'" |
    Where-Object { $_.CommandLine -like "*127.0.0.1:$Port*" -or $_.CommandLine -like "*localhost:$Port*" }
  foreach ($proc in $oldTunnels) {
    Write-Step "Stopping old cloudflared tunnel PID $($proc.ProcessId)"
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
  }

  for ($attempt = 1; $attempt -le 3; $attempt++) {
    Remove-Item -LiteralPath $tunnelOut, $tunnelErr -ErrorAction SilentlyContinue

    Write-Step "Starting Cloudflare quick tunnel for $localUrl (attempt $attempt)"
    $tunnel = Start-Process -FilePath $Cloudflared `
      -ArgumentList "tunnel --protocol http2 --url `"$localUrl`"" `
      -WorkingDirectory $RepoRoot `
      -WindowStyle Hidden `
      -RedirectStandardOutput $tunnelOut `
      -RedirectStandardError $tunnelErr `
      -PassThru
    Write-Step "Started cloudflared PID $($tunnel.Id)"

    $candidateUrl = $null
    for ($i = 1; $i -le 60; $i++) {
      $candidateUrl = Get-QuickTunnelUrl -OutPath $tunnelOut -ErrPath $tunnelErr
      if ($candidateUrl) { break }
      if (($i % 10) -eq 0) {
        Write-Step "Still waiting for Cloudflare quick tunnel URL..."
      }
      Start-Sleep -Seconds 1
    }
    if (-not $candidateUrl) {
      Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
      if ($attempt -eq 3) {
        throw "Could not detect Cloudflare quick tunnel URL. Check $tunnelOut and $tunnelErr."
      }
      continue
    }

    Write-Step "Detected tunnel URL: $candidateUrl"
    try {
      Wait-ForHttpOk "$candidateUrl/api/stats/health" -Attempts 30 -DelaySeconds 2 | Out-Null
      Write-Step "Tunnel health check passed"
      return $candidateUrl
    } catch {
      Write-Step "Tunnel health check failed: $($_.Exception.Message)"
      Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
      if ($attempt -eq 3) {
        throw
      }
      Start-Sleep -Seconds 3
    }
  }
}

function Start-VerifiedLocalTunnel {
  $localTunnelOut = Join-Path $LogsDir "localtunnel-api.out.log"
  $localTunnelErr = Join-Path $LogsDir "localtunnel-api.err.log"
  Remove-Item -LiteralPath $localTunnelOut, $localTunnelErr -ErrorAction SilentlyContinue

  $oldTunnels = Get-CimInstance Win32_Process |
    Where-Object {
      $_.CommandLine -and
      ($_.CommandLine -like "*localtunnel*" -or $_.CommandLine -like "*lt.js*") -and
      ($_.CommandLine -like "*$LocalTunnelSubdomain*" -or $_.CommandLine -like "*--port $Port*")
    }
  foreach ($proc in $oldTunnels) {
    Write-Step "Stopping old localtunnel process PID $($proc.ProcessId)"
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
  }

  Write-Step "Starting localtunnel https://$LocalTunnelSubdomain.loca.lt -> $localUrl"
  $tunnel = Start-Process -FilePath npx.cmd `
    -ArgumentList "-y localtunnel --port $Port --subdomain $LocalTunnelSubdomain" `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $localTunnelOut `
    -RedirectStandardError $localTunnelErr `
    -PassThru
  Write-Step "Started localtunnel wrapper PID $($tunnel.Id)"

  $candidateUrl = $null
  for ($i = 1; $i -le 45; $i++) {
    $candidateUrl = Get-LocalTunnelUrl -OutPath $localTunnelOut -ErrPath $localTunnelErr
    if ($candidateUrl) { break }
    if (($i % 10) -eq 0) {
      Write-Step "Still waiting for localtunnel URL..."
    }
    Start-Sleep -Seconds 1
  }
  if (-not $candidateUrl) {
    throw "Could not detect localtunnel URL. Check $localTunnelOut and $localTunnelErr."
  }

  Write-Step "Detected tunnel URL: $candidateUrl"
  Wait-ForHttpOk "$candidateUrl/api/stats/health" -Attempts 30 -DelaySeconds 2 | Out-Null
  Write-Step "Tunnel health check passed"
  return $candidateUrl
}

if ($TunnelProvider -eq "cloudflare") {
  $tunnelUrl = Start-VerifiedQuickTunnel
} else {
  $tunnelUrl = Start-VerifiedLocalTunnel
}

Write-Step "Updating Netlify production env: local tunnel primary"
& netlify env:set VITE_API_URL $tunnelUrl --context production --force --site $SiteId | Write-Host
& netlify env:set VITE_BACKUP_API_URLS $BackupApiUrls --context production --force --site $SiteId | Write-Host
& netlify env:set VITE_WAKE_BACKEND 1 --context production --force --site $SiteId | Write-Host

if ($NoDeploy) {
  Write-Step "Skipping Netlify deploy because -NoDeploy was passed"
} else {
  Write-Step "Deploying Netlify production with refreshed tunnel URL"
  & netlify deploy --prod --dir=dist --site $SiteId --message "Auto-sync local API tunnel $(Get-Date -Format s)"
  if ($LASTEXITCODE -ne 0) {
    throw "Netlify deploy failed with exit code $LASTEXITCODE"
  }
}

Write-Step "Local API tunnel sync complete: $tunnelUrl"
