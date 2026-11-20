# 숏츠 매일 자동 생성 예약 작업(11/20 운영자 "매일 자동 생성").
# 한국: 평일 16:20(장 마감 뒤) · 미국: 화~토 06:40(미국 장 마감 뒤, 한국 시각). 창 없이 pythonw 로 실행.
# 결과는 바탕화면 trlab_shorts\날짜\ 에 영상·대본·_기록.txt. 업로드·카톡 전송은 하지 않는다.
# PC가 꺼져 있거나 절전이면 그날은 만들어지지 않는다(켜진 뒤 한 번 따라잡기: StartWhenAvailable).
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$py = (Get-Command python).Source
$pyw = Join-Path (Split-Path -Parent $py) "pythonw.exe"
if (-not (Test-Path $pyw)) { $pyw = $py }
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -DontStopIfGoingOnBatteries -AllowStartIfOnBatteries
foreach ($t in @(
    @{ Name = "TRL_Shorts_KR"; Arg = "kr"; At = "16:20"; Days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday") },
    @{ Name = "TRL_Shorts_US"; Arg = "us"; At = "06:40"; Days = @("Tuesday", "Wednesday", "Thursday", "Friday", "Saturday") }
)) {
    $act = New-ScheduledTaskAction -Execute $pyw -Argument "tools\shorts.py --daily $($t.Arg)" -WorkingDirectory $repo
    $trg = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $t.Days -At $t.At
    Register-ScheduledTask -TaskName $t.Name -Action $act -Trigger $trg -Settings $set -Force | Out-Null
    Write-Output "$($t.Name) 등록: $($t.At) $($t.Days -join ',')"
}
