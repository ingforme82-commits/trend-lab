# Register TrendLab realtime health check (every 5 minutes, no window). Result: tools\health.json, problems: tools\healthcheck.log
# Undo: Unregister-ScheduledTask -TaskName TrendLab_HealthCheck -Confirm:$false
$py = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\pythonw.exe'
$act = New-ScheduledTaskAction -Execute $py -Argument 'tools\healthcheck.py' -WorkingDirectory 'C:\projects\trend-lab-site'
$tr = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 4) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'TrendLab_HealthCheck' -Force -Description 'TrendLab realtime health check every 5 min (tools\health.json)' -Action $act -Trigger $tr -Settings $set | Out-Null
Get-ScheduledTask -TaskName 'TrendLab_HealthCheck' | Select-Object TaskName, State
