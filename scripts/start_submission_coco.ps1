# Private interactive CoCo onboarding. Only an isolated fictional database is initialized.
param([switch]$PrepareOnly, [switch]$SubmissionWorkflow)
$ErrorActionPreference = 'Stop'
$host.UI.RawUI.WindowTitle = 'Samvaad 360 - Private CoCo Submission Setup'
$submissionWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $submissionWorkspace
$submissionPython = Join-Path $submissionWorkspace '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $submissionPython)) { throw 'The project Python environment is missing.' }
$submissionRoot = [IO.Path]::GetFullPath((Join-Path $submissionWorkspace '.local\submission-coco'))
$submissionDatabase = [IO.Path]::GetFullPath((Join-Path $submissionRoot 'samvaad.db'))
if (-not $submissionDatabase.StartsWith($submissionRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The isolated submission database path is invalid.'
}
New-Item -ItemType Directory -Force -Path $submissionRoot | Out-Null
$env:SAMVAAD_BACKEND = 'local'
$env:SAMVAAD_DB_PATH = $submissionDatabase
$env:SAMVAAD_COCO_PROOF_PATH = Join-Path $submissionRoot 'hook-events.jsonl'
$env:PATH = (Join-Path $submissionWorkspace '.venv\Scripts') + [IO.Path]::PathSeparator + $env:PATH
& $submissionPython -c "import os; from samvaad.service import LocalService; s=LocalService(os.environ['SAMVAAD_DB_PATH']); print('Isolated fictional CoCo customers: '+str(len(s.list_customers())))"
if ($LASTEXITCODE -ne 0) { throw 'The isolated submission database could not be initialized.' }
Write-Host 'Your existing application database was not reset or changed.'
if ($PrepareOnly) {
    Write-Host 'Private CoCo environment prepared; no Snowflake or model request was made.'
    return
}
$submissionInstallRoot = Join-Path $env:LOCALAPPDATA 'cortex'
$submissionNativeCandidates = @(Get-ChildItem -LiteralPath $submissionInstallRoot -Filter cortex.exe -File -Recurse -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
if ($submissionNativeCandidates.Count -eq 0) { throw 'The native CoCo executable is missing.' }
$submissionCortex = $submissionNativeCandidates[0].FullName
Write-Host ''
Write-Host 'Samvaad 360 - Private CoCo Submission Setup'
Write-Host 'Choose the existing samvaad_hackathon connection in the CoCo wizard.'
Write-Host 'Account: ZYLTUKM-HU63768. User: ARUNVPP24. Enter any password and MFA privately here.'
Write-Host 'Do not paste credentials into chat and do not enable password saving merely for automation.'
if ($SubmissionWorkflow) {
    $submissionPromptPath = Join-Path $submissionRoot 'workflow-prompt.txt'
    if (-not (Test-Path -LiteralPath $submissionPromptPath)) { throw 'The prepared fictional workflow prompt is missing.' }
    Set-Clipboard -Value (Get-Content -LiteralPath $submissionPromptPath -Raw)
    Write-Host 'The fictional three-skill demo prompt is on your clipboard.'
    Write-Host 'After the CoCo conversation opens, press Ctrl+V, then Enter.'
    Write-Host 'Allow only the requested local tools.cli commands. Wait for actual tool output.'
    Write-Host 'Record only after login; keep passwords, tokens and login screens out of video.'
} else {
    Write-Host 'When the CoCo conversation opens, run /skill list. Stop there and leave this terminal open.'
}
Write-Host 'The local application database for this terminal contains only isolated fictional fixtures.'
Write-Host ''
& $submissionCortex --no-auto-update --no-mcp --sql-read-only --private --connection samvaad_hackathon --shell powershell --max-turns 12
