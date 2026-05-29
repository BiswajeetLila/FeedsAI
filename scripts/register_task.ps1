# register_task.ps1
# Registers 3x/day fetch task + weekly profile update task
# Run once as admin (or current user with appropriate permissions)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\register_task.ps1

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

# Find Python in the venv
$PythonPath = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonPath)) {
    Write-Error "Python venv not found at $PythonPath. Run 'uv sync' first."
    exit 1
}

$FetchScript = Join-Path $ProjectRoot "scripts\fetch.py"
$UpdateScript = Join-Path $ProjectRoot "scripts\update_profile.py"
$LogDir = Join-Path $ProjectRoot "logs"

# Create log dir if missing
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# Fetch task: 3x/day at 7am, 1pm, 7pm
$FetchAction = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$FetchScript`"" `
    -WorkingDirectory $ProjectRoot

$FetchTriggers = @(
    $(New-ScheduledTaskTrigger -Daily -At "07:00"),
    $(New-ScheduledTaskTrigger -Daily -At "13:00"),
    $(New-ScheduledTaskTrigger -Daily -At "19:00")
)

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask `
    -TaskName "FeedsAI_Fetch" `
    -Action $FetchAction `
    -Trigger $FetchTriggers `
    -Settings $Settings `
    -Description "FeedsAI: fetch and rank 3x/day" `
    -Force

Write-Host "Registered FeedsAI_Fetch (7am, 1pm, 7pm)"

# Weekly profile update: Sunday at 9am
$UpdateAction = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument "`"$UpdateScript`" --preview" `
    -WorkingDirectory $ProjectRoot

$UpdateTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At "09:00"

Register-ScheduledTask `
    -TaskName "FeedsAI_ProfileUpdate" `
    -Action $UpdateAction `
    -Trigger $UpdateTrigger `
    -Settings $Settings `
    -Description "FeedsAI: weekly profile update proposal" `
    -Force

Write-Host "Registered FeedsAI_ProfileUpdate (Sunday 9am)"
Write-Host "Done. Verify with: Get-ScheduledTask -TaskName 'FeedsAI*'"
