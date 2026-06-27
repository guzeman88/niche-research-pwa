param(
  [string]$LocalUrl = "http://127.0.0.1:8001",
  [string]$LogPath = ""
)

$ErrorActionPreference = "Stop"
$Cloudflared = (Get-Command cloudflared -ErrorAction Stop).Source
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null
if (-not $LogPath) {
  $LogPath = Join-Path $LogsDir "cloudflared-quick-tunnel.log"
}

Write-Host "Starting temporary Cloudflare quick tunnel for $LocalUrl"
Write-Host "Watch for the trycloudflare.com URL in $LogPath"
& $Cloudflared tunnel --url $LocalUrl --logfile $LogPath
