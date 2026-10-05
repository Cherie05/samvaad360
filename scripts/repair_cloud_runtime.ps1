$ErrorActionPreference = 'Stop'
$repairWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $repairWorkspace
$Host.UI.RawUI.WindowTitle = 'Samvaad 360 - Private Cloud Environment Repair'
Write-Host 'Checks the deployed account package catalog and repairs only the app environment.' -ForegroundColor Cyan
Write-Host 'Keep customer tables and demo reviews in place. Enter password/MFA only here; they are hidden and not saved.'
& (Join-Path $repairWorkspace '.venv/Scripts/python.exe') -m scripts.cloud_runtime_repair --account 'ZYLTUKM-HU63768' --user 'ARUNVPP24'
Write-Host 'Result: output/cloud/runtime-repair/result.json'
