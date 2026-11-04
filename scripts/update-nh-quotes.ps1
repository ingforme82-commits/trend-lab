$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$env:PYTHONIOENCODING = 'utf-8'
& python "$root\tools\nh_quotes.py" --publish
exit $LASTEXITCODE
