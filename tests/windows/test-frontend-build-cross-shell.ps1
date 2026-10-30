# F01/A1-01: one source/bundle identity must verify identically in PS5.1 and PS7.
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$sourceVerifier = Join-Path $repo "scripts/windows/verify-frontend-build.ps1"
$pwsh = Get-Command pwsh -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
if (-not $pwsh) {
    $package = Get-AppxPackage Microsoft.PowerShell -ErrorAction SilentlyContinue
    if ($package) { $pwsh = Join-Path $package.InstallLocation "pwsh.exe" }
}
if (-not $pwsh -or -not (Test-Path -LiteralPath $pwsh)) { throw "POWERSHELL_7_REQUIRED" }
$ps51 = "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe"
$head = (& git -C $repo rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) { throw "HEAD_REQUIRED" }
$temporary = Join-Path ([IO.Path]::GetTempPath()) ("hvs-frontend-identity-" + [guid]::NewGuid().ToString("N"))

function Copy-IdentityFixture([string]$Target) {
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    foreach ($directory in @("frontend/src", "frontend/dist")) {
        $destination = Join-Path $Target $directory
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath (Join-Path $repo $directory) -Destination $destination -Recurse
    }
    foreach ($relative in @("config/ports.json", "frontend/package-lock.json", "frontend/package.json",
                             "frontend/index.html", "frontend/vite.config.ts", "frontend/tsconfig.json")) {
        $destination = Join-Path $Target $relative
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item -LiteralPath (Join-Path $repo $relative) -Destination $destination
    }
    $scriptTarget = Join-Path $Target "scripts/windows/verify-frontend-build.ps1"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $scriptTarget) | Out-Null
    Copy-Item -LiteralPath $sourceVerifier -Destination $scriptTarget
    $utf8 = [Text.UTF8Encoding]::new($false)
    [IO.File]::WriteAllText((Join-Path $Target "package-manifest.json"),
        (@{source_commit=$head} | ConvertTo-Json -Compress), $utf8)
}

function Invoke-Verify([string]$Exe, [string]$Root) {
    $script = Join-Path $Root "scripts/windows/verify-frontend-build.ps1"
    $start = New-Object System.Diagnostics.ProcessStartInfo
    $start.FileName = $Exe
    $start.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -RepoRoot `"$Root`" -SkipBootstrap -Diagnostic"
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $start
    $null = $process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()
    return @{code=$process.ExitCode; text=($stdout + $stderr)}
}

function Require-Failure([string]$Name, [scriptblock]$Mutation, [string]$Code) {
    $case = Join-Path $temporary $Name
    Copy-IdentityFixture $case
    & $Mutation $case
    $result = Invoke-Verify $ps51 $case
    if ($result.code -eq 0 -or $result.text -notmatch "FRONTEND_BUNDLE_STALE" -or
        $result.text -notmatch $Code -or $result.text -match "FRONTEND_BUNDLE_VERIFIED") {
        throw "$Name did not refuse with $Code`n$($result.text)"
    }
}

New-Item -ItemType Directory -Force -Path $temporary | Out-Null
try {
    $positive = Join-Path $temporary "positive"
    Copy-IdentityFixture $positive
    $seven = Invoke-Verify $pwsh $positive
    $five = Invoke-Verify $ps51 $positive
    $again = Invoke-Verify $ps51 $positive
    if ($seven.code -ne 0 -or $five.code -ne 0 -or $again.code -ne 0) {
        throw "CROSS_SHELL_POSITIVE_FAILED`nPS7=$($seven.text)`nPS51=$($five.text)`nAGAIN=$($again.text)"
    }
    $sevenDoc = $seven.text.Split("`n") | Where-Object { $_.Trim().StartsWith("{") } | Select-Object -First 1 | ConvertFrom-Json
    $fiveDoc = $five.text.Split("`n") | Where-Object { $_.Trim().StartsWith("{") } | Select-Object -First 1 | ConvertFrom-Json
    if ($sevenDoc.normalized_source_manifest_sha256 -cne $fiveDoc.normalized_source_manifest_sha256 -or
        $sevenDoc.compiled_bundle_digest -cne $fiveDoc.compiled_bundle_digest -or
        -not $sevenDoc.fresh -or -not $fiveDoc.fresh) { throw "CROSS_SHELL_IDENTITY_MISMATCH" }

    Require-Failure "forged-head" { param($root)
        $path=Join-Path $root "frontend/dist/build-info.json"; $doc=Get-Content $path -Raw|ConvertFrom-Json
        $doc.source_commit="0"*40; [IO.File]::WriteAllText($path,($doc|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    } "SOURCE_MISMATCH"
    Require-Failure "tampered-bundle" { param($root)
        $asset=Get-ChildItem (Join-Path $root "frontend/dist/assets") -File|Select-Object -First 1
        [IO.File]::AppendAllText($asset.FullName,"tamper",[Text.UTF8Encoding]::new($false))
    } "BUNDLE_MISMATCH"
    Require-Failure "altered-ports" { param($root)
        [IO.File]::AppendAllText((Join-Path $root "config/ports.json")," ",[Text.UTF8Encoding]::new($false))
    } "SOURCE_MISMATCH"
    Require-Failure "missing-index" { param($root) Remove-Item -LiteralPath (Join-Path $root "frontend/dist/index.html") -Force } "BUILD_MISSING"
    Require-Failure "invalid-manifest" { param($root)
        [IO.File]::WriteAllText((Join-Path $root "frontend/dist/build-info.json"),"{not-json",[Text.UTF8Encoding]::new($false))
    } "MANIFEST_INVALID"
    Require-Failure "wrong-bundle-sha" { param($root)
        $path=Join-Path $root "frontend/dist/build-info.json"; $doc=Get-Content $path -Raw|ConvertFrom-Json
        $doc.bundle_sha256="0"*64; [IO.File]::WriteAllText($path,($doc|ConvertTo-Json),[Text.UTF8Encoding]::new($false))
    } "BUNDLE_MISMATCH"
    Write-Host "FRONTEND_CROSS_SHELL_IDENTITY_PASS PS7=$($sevenDoc.shell_version) PS51=$($fiveDoc.shell_version) INPUT=$($fiveDoc.normalized_source_manifest_sha256) BUNDLE=$($fiveDoc.compiled_bundle_digest)"
} finally {
    if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Recurse -Force }
}
