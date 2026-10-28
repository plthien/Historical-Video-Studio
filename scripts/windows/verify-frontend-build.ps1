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
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Fingerprint([string[]]$Files) {
    $rows=@($Files | Sort-Object -Unique | ForEach-Object {
        $relative=[System.IO.Path]::GetRelativePath($RepoRoot,$_)
        $relative.Replace("\","/") + ":" + (Digest $_)
    })
    $sha=[System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes=[System.Text.Encoding]::UTF8.GetBytes(($rows -join "`n"))
        return [Convert]::ToHexString($sha.ComputeHash($bytes)).ToLowerInvariant()
    } finally { $sha.Dispose() }
}
$sourceAvailable=Test-Path (Join-Path $sourceDir "App.tsx")
if ($sourceAvailable) {
    $files=@(Get-ChildItem $sourceDir -File -Recurse | ForEach-Object FullName)
    foreach ($extra in @("frontend/package-lock.json","frontend/package.json","frontend/index.html",
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
$fresh=$ready -and $stored -and $stored.schema_version -eq "HVSFrontendBuild.v1"
if ($fresh -and $sourceAvailable) {
    $fresh=$stored.input_sha256 -eq $fingerprint -and $stored.source_commit -eq $head
}
if ($fresh -and -not $sourceAvailable) {
    if (-not $head) { throw "Packaged application requires a signed source identity in package-manifest.json." }
    $fresh=$stored.source_commit -eq $head
}
if ($fresh) {
    $fresh=$stored.bundle_sha256 -eq (Digest (Join-Path $dist "index.html"))
}
if (-not $fresh) {
    if (-not $sourceAvailable) { throw "FRONTEND_BUNDLE_STALE: packaged build identity does not match source/package manifest. Re-package the exact checked-out version." }
    if ($SkipBootstrap) { throw "FRONTEND_BUNDLE_STALE: -SkipBootstrap does not permit old/unknown frontend. Launch without -SkipBootstrap to rebuild." }
    Write-Host "FRONTEND_REBUILD_REQUIRED: source inputs or checkout HEAD differ from built UI."
    if (-not (Test-Path (Join-Path $RepoRoot "frontend/node_modules"))) {
        & npm.cmd ci --prefix frontend --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw "Frontend npm ci failed" }
    }
    & npm.cmd run build --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw "Fresh frontend build failed" }
    if (-not (Test-Path (Join-Path $dist "index.html"))) { throw "Missing frontend/dist/index.html after build" }
    $stored=[ordered]@{
        schema_version="HVSFrontendBuild.v1"
        source_commit=$head
        input_sha256=$fingerprint
        bundle_sha256=(Digest (Join-Path $dist "index.html"))
        generated_utc=[DateTime]::UtcNow.ToString("o")
    }
    $stored | ConvertTo-Json | Set-Content -LiteralPath $info -Encoding utf8
}
Write-Host "FRONTEND_BUNDLE_VERIFIED HEAD=$head INPUT=$fingerprint BUNDLE=$($stored.bundle_sha256)"
return $stored
