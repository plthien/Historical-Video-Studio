# Source checkout/frontend bundle identity gate. Designed for native Windows only.
[CmdletBinding()]
param([switch]$SkipBootstrap,[string]$RepoRoot="")
$ErrorActionPreference="Stop"
if (-not $RepoRoot) { $RepoRoot=(Resolve-Path (Join-Path $PSScriptRoot "../..")).Path }
$dist=Join-Path $RepoRoot "frontend/dist"
$info=Join-Path $dist "build-info.json"
$packageManifest=Join-Path $RepoRoot "package-manifest.json"
$sourceDir=Join-Path $RepoRoot "frontend/src"
function Digest([string]$Path) {
    # Must run under stock Windows PowerShell 5.1 in an extracted ZIP.
    # Avoid depending on Get-FileHash being imported into the host runspace.
    $stream=[System.IO.File]::OpenRead($Path)
    $algorithm=[System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace("-","").ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}
function Fingerprint([string[]]$Files) {
    # Windows PowerShell 5.1/.NET Framework: no Path.GetRelativePath / Convert.ToHexString.
    $prefix=[System.IO.Path]::GetFullPath($RepoRoot).TrimEnd([char[]]@('\','/')) + [System.IO.Path]::DirectorySeparatorChar
    $rows=@($Files | Sort-Object -Unique | ForEach-Object {
        $absolute=[System.IO.Path]::GetFullPath($_)
        if (-not $absolute.StartsWith($prefix,[System.StringComparison]::OrdinalIgnoreCase)) {
            throw "Cannot fingerprint file outside repository: $absolute"
        }
        $relative=$absolute.Substring($prefix.Length)
        $relative.Replace('\','/') + ":" + (Digest $absolute)
    })
    $sha=[System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes=[System.Text.Encoding]::UTF8.GetBytes(($rows -join "`n"))
        return ([System.BitConverter]::ToString($sha.ComputeHash($bytes))).Replace("-","").ToLowerInvariant()
    } finally { $sha.Dispose() }
}
function BundleDigest {
    $files=@(Get-ChildItem -LiteralPath $dist -Recurse -File |
        Where-Object { $_.FullName -ne $info } |
        ForEach-Object FullName)
    if ($files.Count -eq 0 -or -not (Test-Path (Join-Path $dist "index.html"))) {
        throw "FRONTEND_BUNDLE_STALE: built index and assets must exist."
    }
    # Hash every published JS/CSS/media file, not just index.html.
    # Exclude only the manifest to prevent a circular SHA dependency.
    return (Fingerprint -Files $files)
}
# A packaged frontend has no TS sources, so its API-origin config must also
# be checked against the compiled bundle manifest (not just the git SHA).
$portsFile=Join-Path $RepoRoot "config/ports.json"
if (-not (Test-Path -LiteralPath $portsFile)) { throw "Missing config/ports.json" }
$portsSha=Digest $portsFile
$sourceAvailable=Test-Path (Join-Path $sourceDir "App.tsx")
if ($sourceAvailable) {
    $files=@(Get-ChildItem $sourceDir -File -Recurse | ForEach-Object FullName)
    foreach ($extra in @("config/ports.json","frontend/package-lock.json","frontend/package.json","frontend/index.html",
                          "frontend/vite.config.ts","frontend/tsconfig.json")) {
        $file=Join-Path $RepoRoot $extra
        if (Test-Path $file) { $files+= $file }
    }
    $fingerprint=Fingerprint $files
} else { $fingerprint=$null }
$head=$null
if (Test-Path (Join-Path $RepoRoot ".git")) {
    $ref=& git -C $RepoRoot rev-parse HEAD 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $ref) { throw "Unable to verify source HEAD before launch." }
    $head="$ref".Trim()
} elseif (Test-Path $packageManifest) {
    $manifest=Get-Content $packageManifest -Raw | ConvertFrom-Json
    $head=$manifest.source_commit
}
$stored=$null
if (Test-Path $info) { try { $stored=Get-Content $info -Raw | ConvertFrom-Json } catch {} }
$ready=Test-Path (Join-Path $dist "index.html")
$fresh=$ready -and $stored -and $stored.schema_version -eq "HVSFrontendBuild.v1" -and $stored.port_config_sha256 -eq $portsSha
if ($fresh -and $sourceAvailable) {
    $fresh=$stored.input_sha256 -eq $fingerprint -and $stored.source_commit -eq $head
}
if ($fresh -and -not $sourceAvailable) {
    if (-not $head) { throw "Packaged application requires a signed source identity in package-manifest.json." }
    $fresh=$stored.source_commit -eq $head
}
if ($fresh) {
    $fresh=$stored.bundle_sha256 -eq (BundleDigest)
}
if (-not $fresh) {
    if (-not $sourceAvailable) { throw "FRONTEND_BUNDLE_STALE: packaged build identity does not match source/package manifest. Re-package the exact checked-out version." }
    if ($SkipBootstrap) { throw "FRONTEND_BUNDLE_STALE: -SkipBootstrap does not permit old/unknown frontend. Launch without -SkipBootstrap to rebuild." }
    Write-Host "FRONTEND_REBUILD_REQUIRED: source inputs or checkout HEAD differ from built UI."
    if (-not (Test-Path (Join-Path $RepoRoot "frontend/node_modules"))) {
        & npm.cmd ci --prefix frontend --no-audit --no-fund | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "Frontend npm ci failed" }
    }
    & npm.cmd run build --prefix frontend | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Fresh frontend build failed" }
    if (-not (Test-Path (Join-Path $dist "index.html"))) { throw "Missing frontend/dist/index.html after build" }
    $stored=[ordered]@{
        schema_version="HVSFrontendBuild.v1"
        source_commit=$head
        input_sha256=$fingerprint
        port_config_sha256=$portsSha
        bundle_sha256=(BundleDigest)
        generated_utc=[DateTime]::UtcNow.ToString("o")
    }
    # Windows PowerShell 5.1's Set-Content -Encoding utf8 writes EF BB BF.
    # Starlette then serves those BOM bytes unchanged, while a 5.1 HTTP client
    # can misdecode them. Emit UTF-8 *without* BOM on every new build.
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    [System.IO.File]::WriteAllText($info, ($stored | ConvertTo-Json -Depth 6), $utf8NoBom)
}
# Recover already-verified old installs without rebuilding assets or touching
# any SQLite data. The manifest is excluded from BundleDigest by design.
if ($fresh) {
    $existingBytes = [System.IO.File]::ReadAllBytes($info)
    if ($existingBytes.Length -ge 3 -and $existingBytes[0] -eq 239 -and
        $existingBytes[1] -eq 187 -and $existingBytes[2] -eq 191) {
        $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($info, ($stored | ConvertTo-Json -Depth 6), $utf8NoBom)
        Write-Host "FRONTEND_MANIFEST_BOM_REMOVED"
    }
}
Write-Host "FRONTEND_BUNDLE_VERIFIED HEAD=$head INPUT=$fingerprint BUNDLE=$($stored.bundle_sha256)"
return $stored
