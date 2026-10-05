$ErrorActionPreference = 'Stop'
$taskWorkspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$Host.UI.RawUI.WindowTitle = 'Samvaad 360 - Public Website Backend'
Set-Location -LiteralPath $taskWorkspace
& (Join-Path $taskWorkspace '.venv\Scripts\python.exe') -X utf8 -m scripts.setup_public_cloud
Write-Host 'Leave this window open and return to the chat. Do not share credentials.'
