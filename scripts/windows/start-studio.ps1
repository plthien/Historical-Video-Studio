# Native Windows launcher for the real FastAPI API and built six-workspace UI.
[CmdletBinding()]
param(
    [switch]$Smoke,
    [switch]$NoBrowser,
    [switch]$SkipBootstrap,
    [int]$Port = 8000,
    [string]$DataRoot = "",
    [string]$EvidencePath = "",
    [string]$VerifyProjectId = ""
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
if (-not $DataRoot) { $DataRoot = Join-Path $repo "data" }
$data = [System.IO.Path]::GetFullPath($DataRoot)
$frontend = Join-Path $repo "frontend\dist"
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
$script:BootstrapPython = $null
$script:BootstrapPrefix = @()
$script:EnvironmentSource = $null
$evidence = [ordered]@{
    schema_version = "HistoricalVideoStudioCleanLaunch.v1"
    package_root = $repo
    data_root = $data
    port = $Port
    skip_bootstrap = [bool]$SkipBootstrap
    api_ready = $false
    ui_status = $null
    project_read = $null
    backend_pid = $null
    process_cleanup = $false
}

function Run-Checked([string]$Name, [string]$Exe, [string[]]$Arguments) {
    Write-Host "==> $Name"
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Name failed with exit code $LASTEXITCODE" }
}
function Require-Version {
    $pythonExe = $null
    $pythonArgs = @()
    if (Test-Path $venvPython) {
        $pythonExe = $venvPython; $pythonArgs = @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        $script:EnvironmentSource = "existing_package_venv"
    } elseif (Get-Command py -ErrorAction SilentlyContinue) {
        $candidate = & py -3.12 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$candidate".Trim() -eq "3.12") {
            $pythonExe = "py"; $pythonArgs = @("-3.12", "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            $script:BootstrapPython = "py"; $script:BootstrapPrefix = @("-3.12")
            $script:EnvironmentSource = "windows_py_3_12"
        }
    }
    if (-not $pythonExe -and (Get-Command python -ErrorAction SilentlyContinue)) {
        $candidate = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($LASTEXITCODE -eq 0 -and "$candidate".Trim() -eq "3.12") {
            $pythonExe = "python"; $pythonArgs = @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
            $script:BootstrapPython = "python"; $script:BootstrapPrefix = @()
            $script:EnvironmentSource = "path_python_3_12"
        }
    }
    if (-not $pythonExe) { throw "Python 3.12 is required (py -3.12)." }
    $python = "$( & $pythonExe @pythonArgs )".Trim()
    if ($LASTEXITCODE -ne 0 -or $python -ne "3.12") { throw "Python 3.12 is required (py -3.12)." }
    $node = (& node -p "process.versions.node.split('.')[0]").Trim()
    if ($LASTEXITCODE -ne 0 -or $node -ne "22") { throw "Node 22 is required." }
    foreach ($tool in @("npm.cmd", "ffmpeg", "ffprobe")) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "$tool is required on PATH." }
    }
}

Push-Location $repo
$backend = $null
try {
    Require-Version
    if (-not $SkipBootstrap) {
        if (-not (Test-Path $venvPython)) {
            if (-not $script:BootstrapPython) { throw "Python 3.12 bootstrap executable is unavailable." }
            Run-Checked "Create Python environment" $script:BootstrapPython @($script:BootstrapPrefix + @("-m", "venv", ".venv"))
        }
        Run-Checked "Install pinned backend" $venvPython @("-m", "pip", "install", "--disable-pip-version-check", "-r", "backend/requirements.lock")
        if (-not (Test-Path (Join-Path $repo "renderer\node_modules"))) { Run-Checked "Install pinned renderer" "npm.cmd" @("ci", "--prefix", "renderer") }
    }
    # Dist/index.html existing does not prove the bundle matches this checkout.
    $build = & (Join-Path $PSScriptRoot "verify-frontend-build.ps1") -RepoRoot $repo -SkipBootstrap:$SkipBootstrap
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "Frontend bundle identity verification failed." }
    $evidence.frontend_source_commit = $build.source_commit
    $evidence.frontend_bundle_sha256 = $build.bundle_sha256
    if (-not (Test-Path $venvPython)) { throw "Missing .venv. Run without -SkipBootstrap first." }
    if (-not (Test-Path (Join-Path $frontend "index.html"))) { throw "Missing frontend build. Run without -SkipBootstrap first." }
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try { $probe.Start() } catch { throw "Port $Port is already in use. Stop the owning process or select -Port." }
    finally { $probe.Stop() }
    New-Item -ItemType Directory -Force -Path $data, (Join-Path $data "media"), (Join-Path $data "logs") | Out-Null
    $env:HVS_DB = Join-Path $data "historical-studio.sqlite"
    $env:HVS_MEDIA = Join-Path $data "media"
    $env:HVS_FRONTEND_DIST = $frontend
    $stdout = Join-Path $data "logs\studio.out.log"
    $stderr = Join-Path $data "logs\studio.err.log"
    $backend = Start-Process -FilePath $venvPython -ArgumentList @("-m", "uvicorn", "backend.app.api.server:app", "--host", "127.0.0.1", "--port", "$Port") -WorkingDirectory $repo -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $deadline = [DateTime]::UtcNow.AddSeconds(45)
    $health = $null
    while ([DateTime]::UtcNow -lt $deadline -and -not $backend.HasExited) {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/health" -TimeoutSec 2
            $ui = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/" -TimeoutSec 2
            if ($health.status -eq "ready" -and $ui.StatusCode -eq 200 -and $ui.Content -match "Historical Video Studio") { break }
        } catch { Start-Sleep -Milliseconds 250 }
    }
    if ($backend.HasExited -or -not $health -or $health.status -ne "ready") {
        throw "Studio failed health/UI readiness. Inspect $stderr"
    }
    $evidence.api_ready = $true
    $evidence.ui_status = $ui.StatusCode
    $evidence.environment_source = $script:EnvironmentSource
    $evidence.backend_pid = $backend.Id
    $manifestPath = Join-Path $repo "package-manifest.json"
    if (Test-Path -LiteralPath $manifestPath) {
        $evidence.source_commit = (Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json).source_commit
    }
    if ($VerifyProjectId) {
        $project = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/api/v1/projects/$VerifyProjectId" -TimeoutSec 5
        $evidence.project_read = [ordered]@{project_id=$project.project_id; project_revision=$project.project_revision}
    }
    $uiBuild = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/build-info.json" -TimeoutSec 5
    if ($uiBuild.bundle_sha256 -ne $build.bundle_sha256 -or $uiBuild.source_commit -ne $build.source_commit) {
        throw "FRONTEND_BUNDLE_STALE: served UI build-info disagrees with verified checkout."
    }
    Write-Host "STUDIO_READY http://127.0.0.1:$Port/ DB=$env:HVS_DB PID=$($backend.Id) UI=$($build.source_commit)"

    if ($Smoke) { Write-Host "STUDIO_SMOKE_PASS"; return }
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$Port/" }
    Write-Host "Press Ctrl+C to stop the local studio."
    Wait-Process -Id $backend.Id
}
finally {
    if ($backend -and -not $backend.HasExited) {
        & taskkill /PID $backend.Id /T /F | Out-Null
        if ($LASTEXITCODE -ne 0 -and -not $backend.HasExited) {
            # Restricted local shells can deny taskkill even for their own
            # child; stopping the exact owned backend remains safe and avoids
            # an orphan in smoke mode.
            Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
        }
        $backend.WaitForExit(10000) | Out-Null
        if ($backend.HasExited) { $evidence.process_cleanup = $true; Write-Host "STUDIO_STOPPED PID=$($backend.Id)" }
        else { Write-Warning "Could not stop studio process tree PID $($backend.Id)." }
    }
    if ($EvidencePath) {
        $target = [System.IO.Path]::GetFullPath($EvidencePath)
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
        $evidence | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $target -Encoding utf8
    }
    Pop-Location
}
