# Build a ZIP/launcher distribution. Python 3.12, Node 22 and FFmpeg remain explicit prerequisites.
[CmdletBinding()]
param([string]$OutputDirectory = "")
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $repo "release\windows" }
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
$rootPrefix = [System.IO.Path]::GetFullPath((Join-Path $repo "release"))
if (-not $output.StartsWith($rootPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Package output must remain below $rootPrefix"
}
function Run-Checked([string]$Name, [string]$Exe, [string[]]$Arguments) {
    Write-Host "==> $Name"; & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}
function Get-Sha256([string]$Path) {
    $stream = [System.IO.File]::OpenRead($Path)
    $algorithm = [System.Security.Cryptography.SHA256]::Create()
    try {
        return ([System.BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace("-", "").ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}
Push-Location $repo
try {
    Run-Checked "Verify pinned Windows environment" "powershell.exe" @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "scripts/windows/verify-environment.ps1")
    Run-Checked "Verify or rebuild exact source-bound frontend" "powershell.exe" @("-NoProfile","-ExecutionPolicy","Bypass","-File","scripts/windows/verify-frontend-build.ps1")
    Run-Checked "Typecheck shared renderer" "npm.cmd" @("run", "typecheck", "--prefix", "renderer")
    $head = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Cannot determine package source commit." }
    New-Item -ItemType Directory -Force -Path $output | Out-Null
    $name = "Historical-Video-Studio-" + $head.Substring(0, 12)
    $stage = Join-Path $output $name
    $zip = Join-Path $output ($name + ".zip")
    foreach ($target in @($stage, $zip)) {
        if (Test-Path -LiteralPath $target) {
            $resolved = (Resolve-Path -LiteralPath $target).Path
            if (-not $resolved.StartsWith($output, [System.StringComparison]::OrdinalIgnoreCase)) { throw "Refusing to replace $resolved" }
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
    New-Item -ItemType Directory -Path $stage | Out-Null
    foreach ($directory in @("backend", "contracts", "renderer", "scripts", "config")) {
        $sourceDir = Join-Path $repo $directory
        $targetDir = Join-Path $stage $directory
        & robocopy $sourceDir $targetDir /E /NFL /NDL /NJH /NJS /XD node_modules .artifacts __pycache__ .pytest_cache /XF *.pyc *.sqlite *.sqlite-wal *.sqlite-shm *.log .env .env.* | Out-Null
        if ($LASTEXITCODE -gt 7) { throw "Copy $directory failed with robocopy exit code $LASTEXITCODE" }
    }
    New-Item -ItemType Directory -Path (Join-Path $stage "frontend") | Out-Null
    Copy-Item -Path (Join-Path $repo "frontend\dist") -Destination (Join-Path $stage "frontend") -Recurse
    Copy-Item -LiteralPath (Join-Path $repo "frontend\package.json") -Destination (Join-Path $stage "frontend")
    Copy-Item -LiteralPath (Join-Path $repo "frontend\package-lock.json") -Destination (Join-Path $stage "frontend")
    foreach ($file in @("README.md", "AGENTS.md")) { Copy-Item -LiteralPath (Join-Path $repo $file) -Destination $stage }
    Get-ChildItem -Path $stage -Directory -Recurse | Where-Object { $_.Name -in @("__pycache__", ".pytest_cache", "node_modules", ".artifacts") } | Sort-Object FullName -Descending | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
    Get-ChildItem -Path $stage -File -Recurse | Where-Object { $_.Name -match "(^\.env|\.sqlite(-wal|-shm)?$|\.log$|\.pyc$)" } | ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force }
    $files = @(Get-ChildItem -Path $stage -File -Recurse | Sort-Object FullName | ForEach-Object {
        [ordered]@{path=$_.FullName.Substring($stage.Length+1).Replace("\", "/"); byte_count=$_.Length; sha256=(Get-Sha256 $_.FullName)}
    })
    $manifest = [ordered]@{schema_version="HistoricalVideoStudioWindowsPackage.v1"; source_commit=$head; artifact_kind="ZIP_WITH_POWERSHELL_LAUNCHER"; bundled=@("application source", "built frontend", "pinned lockfiles"); required=@("Windows 10/11", "Python 3.12", "Node 22/npm 10 or 11", "FFmpeg/ffprobe"); files=$files}
    $manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $stage "package-manifest.json") -Encoding utf8
    Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
    $zipSha = Get-Sha256 $zip
    [ordered]@{status="PACKAGE_PASS"; source_commit=$head; directory=$stage; archive=$zip; archive_sha256=$zipSha; file_count=$files.Count} | ConvertTo-Json -Compress | Write-Host
} finally { Pop-Location }
