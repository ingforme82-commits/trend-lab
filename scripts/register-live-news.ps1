# 트렌드랩_속보갱신 예약 작업 등록(메인 PC). 콘솔 창 없이 1분마다 tools/live_news.py 실행.
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\projects\trend-lab\scripts\register-live-news.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe not found' }
$name = '트렌드랩_속보갱신'
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"' + $root + '\tools\live_news.py"') -WorkingDirectory $root
$triggers = @(
    (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)),
    (New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name))
)
$settings = New-ScheduledTaskSettingsSet -Hidden -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing) {
    Set-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings | Out-Null
} else {
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $settings -Description '속보·시세·주도 섹터 1분마다 수집, 콘솔 창 없음' | Out-Null
}
Start-ScheduledTask -TaskName $name
Write-Output "$name 등록 완료: $pythonw, 1분마다, 로그온 시 재시작, 콘솔 없음"
