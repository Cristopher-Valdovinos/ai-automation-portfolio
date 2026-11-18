# Registers a Windows scheduled task that runs the weekly pipeline every
# Monday at 08:00 and writes a log to data\logs\.
#
# Usage (from the public-buyer-radar folder, in PowerShell):
#   .\scripts\schedule_weekly.ps1                 # Monday 08:00
#   .\scripts\schedule_weekly.ps1 -Time "07:30"   # another time
#
# To remove it:
#   Unregister-ScheduledTask -TaskName "PublicBuyerRadarWeekly" -Confirm:$false

param(
    [string]$Time = "08:00",
    [string]$TaskName = "PublicBuyerRadarWeekly"
)

$project = Split-Path -Parent $PSScriptRoot
$python = Join-Path $project ".venv\Scripts\python.exe"
$logDir = Join-Path $project "data\logs"

if (-not (Test-Path $python)) {
    Write-Error "Python environment not found at $python. Create it first (see README)."
    exit 1
}
New-Item -ItemType Directory -Force $logDir | Out-Null

# The task runs PowerShell, which runs the pipeline and saves all output to a dated log.
$command = "Set-Location '$project'; & '$python' -X utf8 src\run_weekly.py *> ('data\logs\weekly_' + (Get-Date -Format 'yyyy-MM-dd') + '.log')"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -WindowStyle Hidden -Command `"$command`""
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $Time
# Run as soon as possible if the PC was off at the scheduled time.
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
    -Description "Public Buyer Radar: weekly prospect report" -Force | Out-Null

Write-Host "Task '$TaskName' registered: every Monday at $Time."
Write-Host "Logs: $logDir"
Write-Host "Run it now to test:  Start-ScheduledTask -TaskName $TaskName"
