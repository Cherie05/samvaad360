$ErrorActionPreference = 'Stop'
$taskWorkspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskSecrets = Join-Path $taskWorkspace '.local\public-cloud\secrets.toml'
if (-not (Test-Path -LiteralPath $taskSecrets)) { throw 'Run public backend setup first.' }
Set-Clipboard -Value ([System.IO.File]::ReadAllText($taskSecrets))
Write-Host 'Service settings copied. Paste only into Streamlit Cloud Advanced settings > Secrets. Do not paste into chat or GitHub.'
