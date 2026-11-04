$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
$pythonw = Join-Path (Split-Path -Parent (Get-Command python).Source) 'pythonw.exe'
$process = Start-Process -FilePath $pythonw -ArgumentList ('"' + $root + '\tools\nh_quotes.py" --publish --quiet') -WorkingDirectory $root -WindowStyle Hidden -Wait -PassThru
exit $process.ExitCode
