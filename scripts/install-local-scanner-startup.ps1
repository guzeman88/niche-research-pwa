param(
  [int]$Port = 8001,
  [string]$SchedulerMode = "burst",
  [int]$SchedulerBatchSize = 20,
  [int]$CheckIntervalSeconds = 60,
  [string]$TaskName = "NicheResearchLocalScannerWatchdog",
  [switch]$NoStart
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogsDir = Join-Path $RepoRoot "logs"
New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

$WatchdogScript = Join-Path $PSScriptRoot "watch-local-scanner.ps1"
$InstallLog = Join-Path $LogsDir "local-scanner-startup-install.log"
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$actionArgs = @(
  "-NoProfile",
  "-ExecutionPolicy", "Bypass",
  "-WindowStyle", "Hidden",
  "-File", "`"$WatchdogScript`"",
  "-Port", "$Port",
  "-SchedulerMode", "$SchedulerMode",
  "-SchedulerBatchSize", "$SchedulerBatchSize",
  "-CheckIntervalSeconds", "$CheckIntervalSeconds"
) -join " "

$action = New-ScheduledTaskAction `
  -Execute "powershell.exe" `
  -Argument $actionArgs `
  -WorkingDirectory $RepoRoot

$trigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
$settings = New-ScheduledTaskSettingsSet `
  -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit (New-TimeSpan -Days 30) `
  -Hidden `
  -MultipleInstances IgnoreNew `
  -RestartCount 999 `
  -RestartInterval (New-TimeSpan -Minutes 1) `
  -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal `
  -UserId $UserId `
  -LogonType Interactive `
  -RunLevel Limited

Register-ScheduledTask `
  -TaskName $TaskName `
  -Action $action `
  -Trigger $trigger `
  -Settings $settings `
  -Principal $principal `
  -Description "Keeps the Niche Research local backend and keyword scanner running silently after logon." `
  -Force | Out-Null

"[$(Get-Date -Format "yyyy-MM-dd HH:mm:ss")] Installed $TaskName for $UserId at $RepoRoot" |
  Add-Content -Encoding ASCII -Path $InstallLog

if (-not $NoStart) {
  Start-ScheduledTask -TaskName $TaskName
}

$task = Get-ScheduledTask -TaskName $TaskName
Write-Host "Installed scheduled task: $TaskName"
Write-Host "Task state: $($task.State)"
Write-Host "Watchdog log: $(Join-Path $LogsDir "local-scanner-watchdog.log")"
Write-Host "Backend log: $(Join-Path $LogsDir "local-backend.out.log")"
