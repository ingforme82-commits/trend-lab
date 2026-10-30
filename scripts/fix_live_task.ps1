# 트렌드랩_속보갱신 예약 작업 복구: '로그온 때만' 반복하던 트리거에 '지금부터 1분마다(10년)' 트리거를 더한다.
# 실행: powershell -NoProfile -ExecutionPolicy Bypass -File C:\projects\trend-lab-site\scripts\fix_live_task.ps1
$name = '트렌드랩_속보갱신'
$start = (Get-Date).AddMinutes(1).ToString("yyyy-MM-ddTHH:mm:00")
$rep = New-ScheduledTaskTrigger -Once -At $start -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$logon.Repetition = $rep.Repetition
Set-ScheduledTask -TaskName $name -Trigger $rep, $logon | Out-Null
$i = Get-ScheduledTaskInfo -TaskName $name
"복구 완료 · 다음 실행: $($i.NextRunTime)"
