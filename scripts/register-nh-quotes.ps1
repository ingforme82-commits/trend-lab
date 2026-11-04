# NH 현재가를 콘솔 창 없이 1분마다 갱신한다. 현재 사용자 GitHub 인증을 사용한다.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe not found' }
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"' + $root + '\tools\nh_quotes.py" --publish --quiet') -WorkingDirectory $root
$triggers = @(
    (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)),
    (New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name))
)
$settings = New-ScheduledTaskSettingsSet -Hidden -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$existing = Get-ScheduledTask -TaskName 'TRL_NH_Quotes' -ErrorAction SilentlyContinue
if ($existing) {
    Set-ScheduledTask -TaskName 'TRL_NH_Quotes' -Action $action -Trigger $triggers -Settings $settings | Out-Null
} else {
    Register-ScheduledTask -TaskName 'TRL_NH_Quotes' -Action $action -Trigger $triggers -Settings $settings -Description 'NH KORU SOXL current quotes, every minute, no console' | Out-Null
}
Start-ScheduledTask -TaskName 'TRL_NH_Quotes'
Write-Output 'TRL_NH_Quotes: pythonw, every minute, logon restart, no console'
