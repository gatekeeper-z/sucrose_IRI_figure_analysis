$ErrorActionPreference = "Stop"

$RootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RootDir
$LogPath = Join-Path $RootDir "setup_windows.log"
$TranscriptStarted = $false
try {
    Start-Transcript -Path $LogPath -Force | Out-Null
    $TranscriptStarted = $true
} catch {
    Write-Host "Could not start setup log: $($_.Exception.Message)"
}

Write-Host ""
Write-Host "============================================================"
Write-Host " IRI Analyzer - Windows environment setup"
Write-Host "============================================================"
Write-Host "Log file: $LogPath"
Write-Host ""

try {

function Refresh-Path {
    $machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = (@($machinePath, $userPath) | Where-Object { $_ }) -join ";"
}

function Test-PythonCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [string[]]$Arguments = @()
    )
    try {
        & $Command @Arguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py -and (Test-PythonCommand -Command $py.Source -Arguments @("-3"))) {
        return [pscustomobject]@{ Command = $py.Source; Arguments = @("-3"); Display = "$($py.Source) -3" }
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python -and (Test-PythonCommand -Command $python.Source)) {
        return [pscustomobject]@{ Command = $python.Source; Arguments = @(); Display = $python.Source }
    }

    $roots = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python"),
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)}
    ) | Where-Object { $_ -and (Test-Path $_) }

    foreach ($root in $roots) {
        $matches = Get-ChildItem -Path $root -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending
        foreach ($match in $matches) {
            if (Test-PythonCommand -Command $match.FullName) {
                return [pscustomobject]@{ Command = $match.FullName; Arguments = @(); Display = $match.FullName }
            }
        }
    }

    return $null
}

function Test-NodeCommand {
    param([Parameter(Mandatory = $true)][string]$Command)
    try {
        & $Command -e "process.exit(Number(process.versions.node.split('.')[0]) >= 18 ? 0 : 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Find-Node {
    $node = Get-Command node -ErrorAction SilentlyContinue
    if ($node -and (Test-NodeCommand -Command $node.Source)) {
        return $node.Source
    }

    $common = @(
        (Join-Path $env:ProgramFiles "nodejs\node.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\nodejs\node.exe")
    )
    foreach ($path in $common) {
        if ((Test-Path $path) -and (Test-NodeCommand -Command $path)) {
            return $path
        }
    }

    return $null
}

function Find-Npm {
    $npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($npm) { return $npm.Source }

    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($npm) { return $npm.Source }

    $common = @(
        (Join-Path $env:ProgramFiles "nodejs\npm.cmd"),
        (Join-Path $env:LOCALAPPDATA "Programs\nodejs\npm.cmd")
    )
    foreach ($path in $common) {
        if (Test-Path $path) { return $path }
    }

    return $null
}

function Install-WithWinget {
    param(
        [Parameter(Mandatory = $true)][string]$PackageId,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "winget was not found; cannot install $Name automatically."
        return
    }

    Write-Host ""
    Write-Host "Trying to install $Name automatically with winget..."
    & $winget.Source install -e --id $PackageId --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "winget install for $Name did not complete successfully."
    }
    Refresh-Path
}

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [string]$WorkingDirectory = ""
    )

    if ($WorkingDirectory) {
        Push-Location $WorkingDirectory
    }
    try {
        & $FilePath @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Command failed with exit code $LASTEXITCODE`: $FilePath $($Arguments -join ' ')"
        }
    } finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

$python = Find-Python
if (-not $python) {
    Write-Host "Python 3.10+ was not found."
    Install-WithWinget -PackageId "Python.Python.3.12" -Name "Python"
    $python = Find-Python
}
if (-not $python) {
    Write-Host ""
    Write-Host "Python still was not found."
    Write-Host "Opening the Python download page. Install Python 3.10+, then double-click 01_setup_environment.cmd again."
    Start-Process "https://www.python.org/downloads/"
    exit 1
}
Write-Host "Python command: $($python.Display)"

$venvPython = Join-Path $RootDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host ""
    Write-Host "Creating local Python virtual environment: .venv"
    Invoke-Checked -FilePath $python.Command -Arguments ($python.Arguments + @("-m", "venv", ".venv"))
} else {
    Write-Host "Python virtual environment already exists: .venv"
}

if (-not (Test-Path $venvPython)) {
    throw "Virtual environment Python was not created: $venvPython"
}

Write-Host ""
Write-Host "Checking Python dependencies..."
& $venvPython -c "import iri_analyzer, fastapi, uvicorn, cv2, numpy, pandas, yaml, matplotlib" *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing Python package and dependencies..."
    Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "-e", ".")
    Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "pytest")
} else {
    Write-Host "Python dependencies are available."
}

$node = Find-Node
$npm = Find-Npm
if (-not $node -or -not $npm) {
    Write-Host ""
    Write-Host "Node.js 18+ or npm was not found."
    Install-WithWinget -PackageId "OpenJS.NodeJS.LTS" -Name "Node.js LTS"
    $node = Find-Node
    $npm = Find-Npm
}
if (-not $node -or -not $npm) {
    Write-Host ""
    Write-Host "Node.js/npm still was not found."
    Write-Host "Opening the Node.js download page. Install Node.js LTS, then double-click 01_setup_environment.cmd again."
    Start-Process "https://nodejs.org/"
    exit 1
}
Write-Host "Node command: $node"
Write-Host "npm command: $npm"

$packageJson = Join-Path $RootDir "web\package.json"
if (-not (Test-Path $packageJson)) {
    throw "Frontend project was not found: $packageJson"
}

Write-Host ""
Write-Host "Checking frontend dependencies..."
$webDir = Join-Path $RootDir "web"
if (-not (Test-Path (Join-Path $webDir "node_modules"))) {
    Write-Host "Installing frontend dependencies with npm ci..."
    Push-Location $webDir
    try {
        & $npm ci
        if ($LASTEXITCODE -ne 0) {
            Write-Host "npm ci failed; trying npm install..."
            & $npm install
            if ($LASTEXITCODE -ne 0) {
                throw "npm install failed with exit code $LASTEXITCODE"
            }
        }
    } finally {
        Pop-Location
    }
} else {
    Write-Host "Frontend dependencies already exist: web\node_modules"
}

Write-Host ""
Write-Host "Building frontend..."
Invoke-Checked -FilePath $npm -Arguments @("run", "build") -WorkingDirectory $webDir

Write-Host ""
Write-Host "Running quick verification tests..."
Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pip", "install", "pytest", "httpx")
Invoke-Checked -FilePath $venvPython -Arguments @("-m", "pytest", "-q")

Write-Host ""
Write-Host "============================================================"
Write-Host " Setup complete."
Write-Host " You can now double-click 02_start_web_ui.cmd"
Write-Host "============================================================"
exit 0
} catch {
    Write-Host ""
    Write-Host "============================================================"
    Write-Host " Setup failed."
    Write-Host " Error: $($_.Exception.Message)"
    Write-Host " Log file: $LogPath"
    Write-Host "============================================================"
    exit 1
} finally {
    if ($TranscriptStarted) {
        try {
            Stop-Transcript | Out-Null
        } catch {
        }
    }
}
