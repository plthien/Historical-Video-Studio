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
    $venv = Join-Path $repo ".venv"
    $venvPython = Join-Path $venv "Scripts/python.exe"
    if (-not (Test-Path $venvPython)) {
        Run-Checked "Create isolated Python 3.12 venv" "py" @("-3.12", "-m", "venv", $venv)
    }
    # Reject a stale/wrong-interpreter venv; no use of ambient global packages.
    Run-Checked "Verify isolated Python interpreter" $venvPython @("-c", "import sys,pathlib; root=pathlib.Path(r'$repo'); expected=(root/'.venv'/'Scripts'/'python.exe').resolve(); assert sys.version_info[:2]==(3,12) and sys.prefix!=sys.base_prefix and pathlib.Path(sys.executable).resolve()==expected, 'wrong/non-isolated Python'; print('VENV_PYTHON='+sys.executable)")
    if (-not $SkipInstall) {
        # Pip is idempotent for satisfied exact pins; never installs into the global interpreter.
        Run-Checked "Install pinned Python dependencies in .venv" $venvPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", "backend/requirements.lock")
        foreach ($dir in @("frontend", "renderer")) {
            Run-Checked "$dir npm ci" "npm.cmd" @("ci", "--prefix", $dir)
        }
    }
    Run-Checked "Isolated pip dependency consistency" $venvPython @("-m", "pip", "check")
    Run-Checked "Design schemas" $venvPython @("scripts/check_design_contracts.py")
    Run-Checked "Visual contract" $venvPython @("scripts/validate_visual_design.py")
    Run-Checked "Frozen design-contract unittest regressions" $venvPython @("-m", "unittest", "discover", "-s", "tests/contracts", "-p", "test_*.py", "-v")
    Run-Checked "Generate Python/TypeScript types" $venvPython @("scripts/generate_contract_types.py")
    Run-Checked "Check Python/TypeScript types" $venvPython @("scripts/generate_contract_types.py", "--check")
    Run-Checked "Import generated Python types" $venvPython @("-c", "from backend.app.contracts.generated import VisualBlueprint_v1, API_REQUEST_MODELS; assert API_REQUEST_MODELS; print('PYTHON_TYPES_IMPORT_PASS')")
    Run-Checked "TypeScript type assertions/compilation" "npm.cmd" @("run", "typecheck", "--prefix", "frontend")
    Run-Checked "Story import local smoke" $venvPython @("-m", "backend.tools.smoke", "--case", "story-import", "--mode", "local")
    Run-Checked "SQLite cold reopen smoke" $venvPython @("-m", "backend.tools.smoke", "--case", "reopen-project", "--mode", "local")
    Run-Checked "Foundation behavioral tests" $venvPython @("-m", "pytest", "-q", "tests/backend/test_foundation.py")
    foreach ($dir in @("frontend", "renderer")) {
        Run-Checked "$dir Node major" "npm.cmd" @("run", "verify:toolchain", "--prefix", $dir)
    }
    Write-Host "A1 Windows environment and offline behavioral checks PASS"
}
finally { Pop-Location }
