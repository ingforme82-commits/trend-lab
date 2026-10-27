# 트렌드랩 예약 작업 등록(메인 PC, 운영자가 직접 실행)
#   powershell -ExecutionPolicy Bypass -File C:\projects\trend-lab-site\tools\setup_tasks.ps1
# 1) 트렌드랩_깨어있기   : 로그온 시 시작, 전원 연결 중 자동 대기(절전) 방지 — 화면은 꺼짐, 배터리일 땐 동작 안 함
# 2) 트렌드랩_브리핑0720 : 평일 07:20 밤사이 점검 브리핑(대기 중이면 PC를 깨워 실행)
# 3) 트렌드랩_브리핑1400 : 평일 14:00 국내 장중 점검 브리핑(대기 중이면 깨움)
# 3-1) 트렌드랩_브리핑2005·2215 : 평일 20:05(넥장 마감) · 22:15(미국 개장 전) 선물·유가 점검
# 4) 트렌드랩_방문리포트 : 기존 12시 작업에 '깨워서 실행' 켜기
# 되돌리기: Unregister-ScheduledTask -TaskName 트렌드랩_깨어있기 (브리핑0720·브리핑1400도 같은 방식)

$dir = 'C:\projects\trend-lab-site'
$pyw = (Get-ScheduledTask -TaskName '트렌드랩_속보갱신').Actions[0].Execute

$set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName '트렌드랩_깨어있기' -Force -Description '전원 연결 중 자동 대기 방지(화면은 꺼짐)' `
  -Action (New-ScheduledTaskAction -Execute $pyw -Argument 'tools\keep_awake.py' -WorkingDirectory $dir) `
  -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME) -Settings $set | Out-Null
Start-ScheduledTask -TaskName '트렌드랩_깨어있기'

$wake = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -MultipleInstances IgnoreNew
$days = 'Monday','Tuesday','Wednesday','Thursday','Friday'
foreach ($s in @(@('0720','07:20'), @('1400','14:00'), @('2005','20:05'), @('2215','22:15'))) {
  Register-ScheduledTask -TaskName "트렌드랩_브리핑$($s[0])" -Force -Description "정시 브리핑 $($s[1]) (검증 실패 시 발행 차단)" `
    -Action (New-ScheduledTaskAction -Execute $pyw -Argument "tools\brief_slot.py $($s[0])" -WorkingDirectory $dir) `
    -Trigger (New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $s[1]) -Settings $wake | Out-Null
}

# 5) 트렌드랩_종목군 : 매일 23:00·00:00 — 미국 개장 후 20~75분일 때만 '오늘의 주요 종목군' 자동 교체(서머타임 자동)
$tr = @((New-ScheduledTaskTrigger -Daily -At '23:00'), (New-ScheduledTaskTrigger -Daily -At '00:00'))
Register-ScheduledTask -TaskName '트렌드랩_종목군' -Force -Description '미국 개장 30분 뒤 오늘의 주요 종목군 자동 교체' `
  -Action (New-ScheduledTaskAction -Execute $pyw -Argument 'tools\spot_auto.py' -WorkingDirectory $dir) -Trigger $tr -Settings $wake | Out-Null

# 6) 트렌드랩_깃풀 : 10분마다 깃허브 자동 받기(안전 모드 — 고치던 파일 있거나 갈라지면 건드리지 않음)
$pull = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew
$tp = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName '트렌드랩_깃풀' -Force -Description '깃허브 자동 받기(안전 모드)' `
  -Action (New-ScheduledTaskAction -Execute $pyw -Argument 'tools\auto_pull.py' -WorkingDirectory $dir) -Trigger $tp -Settings $pull | Out-Null

$t = Get-ScheduledTask -TaskName '트렌드랩_방문리포트'
$t.Settings.WakeToRun = $true
Set-ScheduledTask -InputObject $t | Out-Null

Get-ScheduledTask -TaskName '트렌드랩_*' | Select-Object TaskName, State | Format-Table -AutoSize
powercfg /requests
