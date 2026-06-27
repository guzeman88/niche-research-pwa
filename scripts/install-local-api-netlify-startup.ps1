param(
  [int]$Port = 8001,
  [string]$SiteId = "9c00efca-ced9-4097-b302-172437380b32",
  [string]$RenderFallbackUrl = "https://niche-research-api-kqlt.onrender.com",
  [ValidateSet("localtunnel", "cloudflare")]
  [string]$TunnelProvider = "localtunnel",
  [string]$LocalTunnelSubdomain = "etsy-niches-api-guzeman88"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$StartupDir = [Environment]::GetFolderPath("Startup")
$StartupFile = Join-Path $StartupDir "NicheResearchLocalApiSync.bat"
$SyncScript = Join-Path $PSScriptRoot "start-local-api-and-sync-netlify.ps1"
$StartupLog = Join-Path $LogsDir "local-api-netlify-sync-startup.log"

@"
@echo off
cd /d "$RepoRoot"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$SyncScript" -Port $Port -SiteId "$SiteId" -RenderFallbackUrl "$RenderFallbackUrl" -TunnelProvider "$TunnelProvider" -LocalTunnelSubdomain "$LocalTunnelSubdomain" >> "$StartupLog" 2>&1
"@ | Set-Content -Encoding ASCII -Path $StartupFile

Write-Host "Installed startup sync:"
Write-Host "  $StartupFile"
Write-Host "Startup log:"
Write-Host "  $StartupLog"
