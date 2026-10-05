$ErrorActionPreference = 'Stop'
$workspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $workspace '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing project .venv Python interpreter.'
}
& $python (Join-Path $PSScriptRoot 'stop_local.py')
exit $LASTEXITCODE
