# Install the official native binary with a verified manifest checksum.
# Existing installations and user PATH are preserved; no account login occurs.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$cocoRepository = 'https://sfc-repo.snowflakecomputing.com/cortex-code-cli/a4643c4278'
$cocoVersion = (Invoke-WebRequest -Uri "$cocoRepository/stable_version.txt" -UseBasicParsing).Content.Trim()
if ($cocoVersion -notmatch '^\d+\.\d+\.\d+[A-Za-z0-9.+_-]*$') { throw 'Unexpected official release version.' }
$cocoEncodedVersion = [Uri]::EscapeDataString($cocoVersion)
$cocoManifest = (Invoke-WebRequest -Uri "$cocoRepository/$cocoEncodedVersion/manifest.json" -UseBasicParsing).Content | ConvertFrom-Json
$cocoArchitecture = if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'amd64' }
$cocoPackage = $cocoManifest.packages.windows.$cocoArchitecture
if (-not $cocoPackage -or $cocoPackage.name -notmatch '^[A-Za-z0-9.+_-]+\.tar\.gz$') { throw 'Native Windows release unavailable.' }
$cocoWorkspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cocoDownloadDir = Join-Path $cocoWorkspace '.local/installers'
New-Item -ItemType Directory -Force -Path $cocoDownloadDir | Out-Null
$cocoArchive = Join-Path $cocoDownloadDir 'coco-official.tar.gz'
Invoke-WebRequest -Uri "$cocoRepository/$cocoEncodedVersion/$([Uri]::EscapeDataString($cocoPackage.name))" -OutFile $cocoArchive -UseBasicParsing
if ((Get-FileHash -LiteralPath $cocoArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $cocoPackage.checksum.ToLowerInvariant()) { throw 'Official archive checksum mismatch.' }
$cocoExtractionRoot = Join-Path $cocoDownloadDir ('coco-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $cocoExtractionRoot | Out-Null
$cocoMembers = & tar -tzf $cocoArchive
if ($LASTEXITCODE -ne 0) { throw 'Cannot inspect official archive.' }
foreach ($cocoMember in $cocoMembers) {
    if ($cocoMember -match '(^[/\\]|(^|[/\\])\.\.([/\\]|$)|^[A-Za-z]:)') { throw 'Unsafe archive member path.' }
}
& tar -xzf $cocoArchive -C $cocoExtractionRoot
if ($LASTEXITCODE -ne 0) { throw 'Native archive extraction failed; files retained for inspection.' }
$cocoExtracted = @(Get-ChildItem -LiteralPath $cocoExtractionRoot -Directory)
if ($cocoExtracted.Count -ne 1 -or -not (Test-Path -LiteralPath (Join-Path $cocoExtracted[0].FullName 'cortex.exe'))) { throw 'Unexpected native package layout.' }
$cocoInstallRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'cortex'))
$cocoInstallTarget = [IO.Path]::GetFullPath((Join-Path $cocoInstallRoot $cocoVersion))
if (-not $cocoInstallTarget.StartsWith($cocoInstallRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Install target outside the intended directory.' }
New-Item -ItemType Directory -Force -Path $cocoInstallRoot | Out-Null
if (-not (Test-Path -LiteralPath $cocoInstallTarget)) {
    # Both resolved source and target were checked. No existing version is deleted.
    $cocoSource = [IO.Path]::GetFullPath($cocoExtracted[0].FullName)
    if (-not $cocoSource.StartsWith($cocoExtractionRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Extraction source outside the inspected directory.' }
    Move-Item -LiteralPath $cocoSource -Destination $cocoInstallTarget
}
$cocoBinary = Join-Path $cocoInstallTarget 'cortex.exe'
& $cocoBinary --version
if ($LASTEXITCODE -ne 0) { throw 'Installed binary did not report its version.' }
$cocoReportDir = Join-Path $cocoWorkspace 'output/cloud'
New-Item -ItemType Directory -Force -Path $cocoReportDir | Out-Null
@{version=$cocoVersion; binary=$cocoBinary; official_archive_sha256=$cocoPackage.checksum; account_contacted=$false; model_request_made=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $cocoReportDir 'coco-install.json') -Encoding UTF8
Write-Host "CoCo installed: $cocoBinary"
Write-Host 'User PATH was preserved. Project cloud_coco_check can discover this native version.'

