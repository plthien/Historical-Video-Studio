# Native Windows PowerShell 5.1 regression for frontend build-info JSON encoding.
# Does not require an HTTP server or any provider credentials.
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
. (Join-Path $root "scripts/windows/read-frontend-manifest.ps1")
$manifest = [ordered]@{
    schema_version = "HVSFrontendBuild.v1"
    source_commit = ("a" * 40)
    input_sha256 = ("b" * 64)
    port_config_sha256 = ("c" * 64)
    bundle_sha256 = ("d" * 64)
}
$json = $manifest | ConvertTo-Json -Compress
$noBom = [System.Text.UTF8Encoding]::new($false, $true)
$plain = $noBom.GetBytes($json)
$withBom = [byte[]](@(239, 187, 191) + @($plain))
foreach ($testBytes in @($plain, $withBom)) {
    $decoded = ConvertFrom-HvsFrontendManifestBytes -Bytes $testBytes
    if ($decoded.source_commit -cne $manifest.source_commit -or
        $decoded.bundle_sha256 -cne $manifest.bundle_sha256) {
        throw "FRONTEND_MANIFEST_UTF8_TEST_FAIL: BOM and no-BOM must preserve exact SHA."
    }
}
function Assert-Rejected([byte[]]$Bytes, [string]$Label) {
    $rejected = $false
    try {
        $value = ConvertFrom-HvsFrontendManifestBytes -Bytes $Bytes
        if ($null -ne $value) { Write-Host "Unexpected manifest accepted in $Label" }
    } catch {
        if ("$_" -like "*FRONTEND_BUNDLE_HTTP_INVALID*") { $rejected = $true }
        else { throw }
    }
    if (-not $rejected) { throw "FRONTEND_MANIFEST_NEGATIVE_TEST_FAIL: $Label" }
}
Assert-Rejected -Bytes ($noBom.GetBytes("<!doctype html><title>200 OK</title>")) -Label "HTTP HTML"
Assert-Rejected -Bytes ([byte[]](255,254,253)) -Label "invalid UTF-8"
Assert-Rejected -Bytes ($noBom.GetBytes('{"schema_version":"HVSFrontendBuild.v1"}')) -Label "missing SHA"
Assert-Rejected -Bytes ($noBom.GetBytes('["not a manifest"]')) -Label "JSON array"
Assert-Rejected -Bytes ($noBom.GetBytes('"not a manifest"')) -Label "JSON primitive"
$badSha = $json.Replace(("d" * 64),("x" * 64))
Assert-Rejected -Bytes ($noBom.GetBytes($badSha)) -Label "invalid checksum syntax"
$misleading = $noBom.GetBytes([char]0xFEFF + $json)
$decoded = ConvertFrom-HvsFrontendManifestBytes -Bytes $misleading
if ($decoded.bundle_sha256 -cne $manifest.bundle_sha256) {
    throw "FRONTEND_MANIFEST_UTF8_TEST_FAIL: leading Unicode BOM not handled."
}
Write-Host "FRONTEND_MANIFEST_UTF8_BOM_AND_INVALID_JSON_PASS"
