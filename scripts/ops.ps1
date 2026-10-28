# 트렌드랩 운영 명령(Claude 사용량이 다 찼을 때 Codex·운영자가 PowerShell에서 이어서 사용). 자세한 설명: AGENTS.md '사용량 초과 시'
# 예) powershell -NoProfile -ExecutionPolicy Bypass -File C:\projects\trend-lab-site\scripts\ops.ps1 status
param(
    [Parameter(Position = 0)][ValidateSet("status", "run", "watch", "issue", "issue-remove", "alias", "test", "push", "help")][string]$Cmd = "help",
    [string]$Memo, [double]$Soxl, [double]$Koru, [string]$Title, [string]$Date,
    [string]$Tag, [string]$Points, [string]$Source, [string]$When, [string]$Until,
    [string]$Pattern, [string]$Name, [string]$Message, [switch]$Push
)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if ($Cmd -eq "help") { Get-Content "$root\tools\ops.py" -Encoding UTF8 -TotalCount 14 | Select-Object -Skip 1; exit 0 }
$a = @("tools\ops.py", $Cmd)
if ($PSBoundParameters.ContainsKey("Memo"))    { $a += @("--memo", $Memo) }
if ($PSBoundParameters.ContainsKey("Soxl"))    { $a += @("--soxl", $Soxl) }
if ($PSBoundParameters.ContainsKey("Koru"))    { $a += @("--koru", $Koru) }
if ($Title)   { $a += @("--title", $Title) }
if ($Date)    { $a += @("--date", $Date) }
if ($Tag)     { $a += @("--tag", $Tag) }
if ($Points)  { $a += @("--points", $Points) }
if ($Source)  { $a += @("--source", $Source) }
if ($When)    { $a += @("--when", $When) }
if ($Until)   { $a += @("--until", $Until) }
if ($Pattern) { $a += @("--pattern", $Pattern) }
if ($Name)    { $a += @("--name", $Name) }
if ($Message) { $a += @("--message", $Message) }
if ($Push)    { $a += "--push" }
& python @a
exit $LASTEXITCODE
