# Windows-only A1 contract/DB bootstrap and behavioral smoke. Stop on FIRST failure.
[CmdletBinding()]
param([switch]$SkipInstall)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Push-Location $repo
try {
    function Run-Checked([string]$Name, [string]$Exe, [string[]]$Arguments) {
        Write-Host "==> $Name"
        & $Exe @Arguments
        if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
    }
    $python = (& py -3.12 -c "import sys; print(sys.version_info.major, sys.version_info.minor)").Trim()
    if ($LASTEXITCODE -ne 0 -or $python -ne "3 12") { throw "Python 3.12 is required: py -3.12" }
    $nodeMajor = (& node -p "process.versions.node.split('.')[0]").Trim()
    if ($LASTEXITCODE -ne 0 -or $nodeMajor -ne "22") { throw "Node 22 is required" }
    $npmMajor = (& npm --version).Trim().Split('.')[0]
    if ($LASTEXITCODE -ne 0 -or [int]$npmMajor -lt 10 -or [int]$npmMajor -ge 12) { throw "npm 10/11 required" }
    foreach ($app in @("ffmpeg", "ffprobe")) {
        if (-not (Get-Command $app -ErrorAction SilentlyContinue)) { throw "$app not found on PATH" }
        Run-Checked "$app version" $app @("-version")
    }
    if (-not $SkipInstall) {
        Run-Checked "Python locked dependencies" "py" @("-3.12", "-m", "pip", "install", "-r", "backend/requirements.lock")
        foreach ($dir in @("frontend", "renderer")) {
            Run-Checked "$dir npm ci" "npm.cmd" @("ci", "--prefix", $dir)
        }
    }
    Run-Checked "Design schemas" "py" @("-3.12", "scripts/check_design_contracts.py")
    Run-Checked "Visual contract" "py" @("-3.12", "scripts/validate_visual_design.py")
    Run-Checked "Generate Python/TypeScript types" "py" @("-3.12", "scripts/generate_contract_types.py")
    Run-Checked "Check Python/TypeScript types" "py" @("-3.12", "scripts/generate_contract_types.py", "--check")
    Run-Checked "Story import local smoke" "py" @("-3.12", "-m", "backend.tools.smoke", "--case", "story-import", "--mode", "local")
    Run-Checked "SQLite cold reopen smoke" "py" @("-3.12", "-m", "backend.tools.smoke", "--case", "reopen-project", "--mode", "local")
    Run-Checked "Foundation behavioral tests" "py" @("-3.12", "-m", "pytest", "-q", "tests/backend/test_foundation.py")
    foreach ($dir in @("frontend", "renderer")) {
        Run-Checked "$dir Node major" "npm.cmd" @("run", "verify:toolchain", "--prefix", $dir)
    }
    Write-Host "A1 Windows environment and offline behavioral checks PASS"
}
finally { Pop-Location }
