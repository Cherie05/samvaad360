# Interactive private login. Never redirect this terminal's input or ask for
# passwords/MFA codes in chat. Account identifiers below are non-secret.
$ErrorActionPreference = 'Stop'
$cloudWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Set-Location -LiteralPath $cloudWorkspace
$Host.UI.RawUI.WindowTitle = 'Samvaad 360 - Private Snowflake Cloud Setup'
Write-Host 'Samvaad 360 hackathon cloud setup' -ForegroundColor Cyan
Write-Host 'Account: ZYLTUKM-HU63768 | Login: ARUNVPP24'
Write-Host 'Creates an X-Small warehouse, a 5-credit daily warehouse monitor, synthetic data and a private Streamlit website.'
Write-Host 'Financial delivery and real calls stay disabled. No payment method or account upgrade is changed.'
Write-Host 'Enter your password and authenticator-app code ONLY in this terminal. They are hidden and not saved.'
Write-Host ''
& (Join-Path $cloudWorkspace '.venv/Scripts/python.exe') -m scripts.trial_cloud_setup --account 'ZYLTUKM-HU63768' --user 'ARUNVPP24' --apply
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Open Snowsight > Projects > Streamlit > SAMVAAD360 using role SAMVAAD_HACKATHON.' -ForegroundColor Green
    Write-Host 'Verify Customer 360, Ask with evidence, Review queue and Conversation handoff.'
} else {
    Write-Host 'Setup did not finish. Share only the short error/status code; keep credentials private.' -ForegroundColor Yellow
}
Write-Host 'Result, if the connection was established: output/cloud/trial/result.json'

