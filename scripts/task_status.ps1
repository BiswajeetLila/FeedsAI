# task_status.ps1 — show Task Scheduler status for FeedsAI tasks
# Usage: powershell -File scripts\task_status.ps1

$tasks = Get-ScheduledTask -TaskName "FeedsAI*" -ErrorAction SilentlyContinue

if (-not $tasks) {
    Write-Host "No FeedsAI tasks registered. Run register_task.ps1 first."
    exit 1
}

foreach ($task in $tasks) {
    $info = Get-ScheduledTaskInfo -TaskName $task.TaskName
    Write-Host ""
    Write-Host "Task: $($task.TaskName)"
    Write-Host "  State:      $($task.State)"
    Write-Host "  Last run:   $($info.LastRunTime)"
    Write-Host "  Last exit:  $($info.LastTaskResult)"
    Write-Host "  Next run:   $($info.NextRunTime)"
}
