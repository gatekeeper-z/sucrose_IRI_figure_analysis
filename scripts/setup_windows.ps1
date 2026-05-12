param(
    [switch]$PauseOnExit
)

$ErrorActionPreference = "Stop"

function Test-LaunchedFromExplorer {
    try {
        $current = Get-CimInstance Win32_Process -Filter "ProcessId=$PID" -ErrorAction Stop
        if (-not $current.ParentProcessId) { return $false }
        $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($current.ParentProcessId)" -ErrorAction Stop
        return $parent.Name -ieq "explorer.exe"
    } catch {
        return $false
    }
}

$PauseBeforeExit = $PauseOnExit -or (Test-LaunchedFromExplorer)

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

function Split-PathEntries {
    param([AllowNull()][string]$Value)
    if ([string]::IsNullOrWhiteSpace($Value)) { return @() }

    return @($Value -split ";" | ForEach-Object {
        $entry = $_.Trim().Trim('"')
        if ($entry) {
            [Environment]::ExpandEnvironmentVariables($entry)
        }
    } | Where-Object { $_ })
}

function Add-PathEntry {
    param(
        [System.Collections.Generic.List[string]]$Entries,
        [hashtable]$Seen,
        [AllowNull()][string]$Entry
    )

    if ([string]::IsNullOrWhiteSpace($Entry)) { return }
    $expanded = [Environment]::ExpandEnvironmentVariables($Entry.Trim().Trim('"'))
    if ([string]::IsNullOrWhiteSpace($expanded)) { return }
    $key = $expanded.TrimEnd("\").ToLowerInvariant()
    if (-not $Seen.ContainsKey($key)) {
        $Seen[$key] = $true
        $Entries.Add($expanded) | Out-Null
    }
}

function Refresh-Path {
    $entries = [System.Collections.Generic.List[string]]::new()
    $seen = @{}

    $knownFirst = @(
        (Join-Path $env:SystemRoot "System32"),
        $env:SystemRoot,
        (Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0"),
        (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps"),
        (Join-Path $env:USERPROFILE "AppData\Local\Microsoft\WindowsApps")
    )

    foreach ($entry in $knownFirst) {
        Add-PathEntry -Entries $entries -Seen $seen -Entry $entry
    }

    foreach ($entry in (Split-PathEntries ([Environment]::GetEnvironmentVariable("Path", "Machine")))) {
        Add-PathEntry -Entries $entries -Seen $seen -Entry $entry
    }
    foreach ($entry in (Split-PathEntries ([Environment]::GetEnvironmentVariable("Path", "User")))) {
        Add-PathEntry -Entries $entries -Seen $seen -Entry $entry
    }
    foreach ($entry in (Split-PathEntries $env:Path)) {
        Add-PathEntry -Entries $entries -Seen $seen -Entry $entry
    }

    $env:Path = $entries -join ";"
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

function Test-WingetCommand {
    param([Parameter(Mandatory = $true)][string]$Command)

    try {
        & $Command --version *> $null
        if ($LASTEXITCODE -eq 0) { return $true }
    } catch {
    }

    try {
        & $Command --help *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Add-WingetCandidate {
    param(
        [System.Collections.Generic.List[string]]$Candidates,
        [hashtable]$Seen,
        [AllowNull()][string]$Candidate
    )

    if ([string]::IsNullOrWhiteSpace($Candidate)) { return }
    $key = $Candidate.ToLowerInvariant()
    if (-not $Seen.ContainsKey($key)) {
        $Seen[$key] = $true
        $Candidates.Add($Candidate) | Out-Null
    }
}

function Find-Winget {
    Refresh-Path

    $candidates = [System.Collections.Generic.List[string]]::new()
    $seen = @{}

    foreach ($name in @("winget.exe", "winget")) {
        $commands = @(Get-Command $name -All -ErrorAction SilentlyContinue)
        foreach ($command in $commands) {
            if ($command.Source) {
                Add-WingetCandidate -Candidates $candidates -Seen $seen -Candidate $command.Source
            } elseif ($command.Path) {
                Add-WingetCandidate -Candidates $candidates -Seen $seen -Candidate $command.Path
            } else {
                Add-WingetCandidate -Candidates $candidates -Seen $seen -Candidate $name
            }
        }
    }

    $explicitAliases = @(
        (Join-Path $env:LOCALAPPDATA "Microsoft\WindowsApps\winget.exe"),
        (Join-Path $env:USERPROFILE "AppData\Local\Microsoft\WindowsApps\winget.exe")
    )
    foreach ($path in $explicitAliases) {
        if ($path -and (Test-Path $path)) {
            Add-WingetCandidate -Candidates $candidates -Seen $seen -Candidate $path
        }
    }

    try {
        $packages = @(Get-AppxPackage -Name Microsoft.DesktopAppInstaller -ErrorAction SilentlyContinue |
            Sort-Object Version -Descending)
        foreach ($package in $packages) {
            if ($package.InstallLocation) {
                $packageWinget = Join-Path $package.InstallLocation "winget.exe"
                if (Test-Path $packageWinget) {
                    Add-WingetCandidate -Candidates $candidates -Seen $seen -Candidate $packageWinget
                }
            }
        }
    } catch {
    }

    try {
        $windowsAppsRoot = Join-Path $env:ProgramFiles "WindowsApps"
        if (Test-Path $windowsAppsRoot) {
            $packageDirs = @(Get-ChildItem -Path $windowsAppsRoot -Directory -Filter "Microsoft.DesktopAppInstaller_*" -ErrorAction SilentlyContinue |
                Sort-Object Name -Descending)
            foreach ($dir in $packageDirs) {
                $packageWinget = Join-Path $dir.FullName "winget.exe"
                if (Test-Path $packageWinget) {
                    Add-WingetCandidate -Candidates $candidates -Seen $seen -Candidate $packageWinget
                }
            }
        }
    } catch {
    }

    Add-WingetCandidate -Candidates $candidates -Seen $seen -Candidate "winget.exe"
    Add-WingetCandidate -Candidates $candidates -Seen $seen -Candidate "winget"

    Write-Host "Checking winget candidates..."
    foreach ($candidate in $candidates) {
        if (Test-WingetCommand -Command $candidate) {
            Write-Host "winget command: $candidate"
            return $candidate
        }
        Write-Host "winget candidate did not work: $candidate"
    }

    return $null
}

function Install-WithWinget {
    param(
        [Parameter(Mandatory = $true)][string]$PackageId,
        [Parameter(Mandatory = $true)][string]$Name
    )

    $winget = Find-Winget
    if (-not $winget) {
        Write-Host "winget was not found; cannot install $Name automatically."
        Write-Host "Checked refreshed PATH, WindowsApps aliases, and Microsoft.DesktopAppInstaller."
        return $false
    }

    Write-Host ""
    Write-Host "Trying to install $Name automatically with winget: $winget"
    & $winget install -e --id $PackageId --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Write-Host "winget install for $Name did not complete successfully."
        return $false
    }
    Refresh-Path
    return $true
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
    if ($PauseBeforeExit) {
        Write-Host ""
        $null = Read-Host "Press Enter to close this window"
    }
}
