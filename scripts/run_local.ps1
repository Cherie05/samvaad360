$ErrorActionPreference = 'Stop'
$workspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$python = Join-Path $workspace '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Missing .venv. Install project dependencies using the README first.'
}
$local = Join-Path $workspace '.local'
New-Item -ItemType Directory -Path $local -Force | Out-Null
$script = Join-Path $PSScriptRoot 'run_local.py'
$outLog = Join-Path $local 'supervisor.out.log'
$errLog = Join-Path $local 'supervisor.err.log'
$process = Start-Process -FilePath $python -ArgumentList @('"' + $script + '"') -WorkingDirectory $workspace -WindowStyle Hidden -RedirectStandardOutput $outLog -RedirectStandardError $errLog -PassThru
Write-Output "Local supervisor PID: $($process.Id). App: http://127.0.0.1:8501. API: http://127.0.0.1:8000/docs."
Write-Output 'Use scripts\stop_local.ps1 to stop only this workspace. Check .local logs if startup fails.'
