param([switch]$RepairReviewedSubject)
$ErrorActionPreference = 'Stop'
$githubCloudWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $githubCloudWorkspace
$Host.UI.RawUI.WindowTitle = 'Samvaad 360 - Connect GitHub'
Write-Host 'Connect GitHub to your Snowflake hackathon app' -ForegroundColor Cyan
Write-Host 'Account: ZYLTUKM-HU63768 | Private repository: Cherie05/samvaad360'
Write-Host 'Enter your Snowflake password and MFA privately below. No SQL knowledge is needed.'
if ($RepairReviewedSubject) {
    Write-Host 'Corrects only the exact repository identity for the deployment user just created.' -ForegroundColor Yellow
    & (Join-Path $githubCloudWorkspace '.venv/Scripts/python.exe') -m scripts.connect_github_cloud --repair-reviewed-subject
} else {
    & (Join-Path $githubCloudWorkspace '.venv/Scripts/python.exe') -m scripts.connect_github_cloud
}
Write-Host 'Return to the chat. Result is saved without credentials in output/cloud/github-connection.json.'
