param(
  [Parameter(Mandatory = $true)]
  [string]$Hostname,
  [string]$TunnelName = "etsy-niches-api",
  [string]$LocalUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$Cloudflared = (Get-Command cloudflared -ErrorAction Stop).Source
$CloudflaredDir = Join-Path $env:USERPROFILE ".cloudflared"
$CertPath = Join-Path $CloudflaredDir "cert.pem"
$ConfigPath = Join-Path $CloudflaredDir "$TunnelName.yml"

New-Item -ItemType Directory -Force -Path $CloudflaredDir | Out-Null

if (-not (Test-Path $CertPath)) {
  Write-Host "Cloudflare is not logged in yet. A browser window will open."
  Write-Host "Choose the Cloudflare zone that owns $Hostname, then run this script again."
  & $Cloudflared tunnel login
  exit 0
}

$existing = & $Cloudflared tunnel list 2>$null | Select-String -Pattern $TunnelName
if (-not $existing) {
  & $Cloudflared tunnel create $TunnelName
}

$tunnelInfo = & $Cloudflared tunnel list | Select-String -Pattern $TunnelName | Select-Object -First 1
if (-not $tunnelInfo) {
  throw "Could not find tunnel $TunnelName after create/list."
}

$credentials = Get-ChildItem $CloudflaredDir -Filter "*.json" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
if (-not $credentials) {
  throw "Could not find Cloudflare tunnel credentials JSON in $CloudflaredDir."
}

@"
tunnel: $TunnelName
credentials-file: $($credentials.FullName)

ingress:
  - hostname: $Hostname
    service: $LocalUrl
  - service: http_status:404
"@ | Set-Content -Encoding ASCII -Path $ConfigPath

& $Cloudflared tunnel route dns $TunnelName $Hostname

Write-Host "Created tunnel config: $ConfigPath"
Write-Host "Run the backend, then start the tunnel with:"
Write-Host "  cloudflared tunnel --config `"$ConfigPath`" run $TunnelName"
Write-Host ""
Write-Host "Use this API URL in Netlify/GitHub:"
Write-Host "  https://$Hostname"
