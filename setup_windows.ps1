# SAM Windows source-based developer setup.
# Builds the same Tauri desktop client as macOS; it does not install a
# separately supervised Python backend. Run from PowerShell in the checkout.
$ErrorActionPreference = "Stop"
$setupStage = "prerequisites"
trap {
    if ($pythonExe -and $manager -and $setupStage) {
        & $pythonExe $manager record-step $setupStage blocked --detail "Setup stopped: $($_.Exception.Message)" | Out-Null
    }
    throw
}
$scriptDir = $PSScriptRoot
Set-Location $scriptDir

foreach ($tool in @("node", "npm", "cargo")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Missing $tool. Install Node.js and the Rust toolchain, then rerun setup_windows.ps1."
    }
}

$launcher = Get-Command py -ErrorAction SilentlyContinue
$bootstrap = Get-Command python -ErrorAction SilentlyContinue
if ($launcher) {
    $bootstrapPython = (& py -3 -c "import sys; print(sys.executable)").Trim()
} elseif ($bootstrap) {
    $bootstrapPython = $bootstrap.Source
} else {
    throw "No Python bootstrap or Windows py launcher is available. Install a version supported in compatibility/manifest.json and rerun."
}
$pythonExe = (& $bootstrapPython (Join-Path $scriptDir "runtime\compatibility.py") select-python).Trim()
if ($LASTEXITCODE -ne 0 -or -not $pythonExe) {
    throw "SAM requires one of the supported Python versions in compatibility/manifest.json. Install one of those versions, then rerun."
}
& $pythonExe (Join-Path $scriptDir "runtime\compatibility.py") check-platform --os windows
if ($LASTEXITCODE -ne 0) { throw "This Windows version or architecture is outside SAM's compatibility policy." }
& $pythonExe (Join-Path $scriptDir "runtime\compatibility.py") check-requirements
if ($LASTEXITCODE -ne 0) { throw "Dependency declarations do not satisfy SAM's compatibility policy." }
& $pythonExe (Join-Path $scriptDir "runtime\compatibility.py") check-tools node npm rust
if ($LASTEXITCODE -ne 0) { throw "Desktop build tools do not satisfy SAM's compatibility policy." }

$installGroups = @("core")
foreach ($group in @("voice", "vision", "memory", "integrations")) {
    $answer = Read-Host "Install optional '$group' dependencies now? [y/N]"
    if ($answer -match '^[Yy]$') { $installGroups += $group }
}
if ($installGroups -contains "voice") {
    $voicePrerequisites = & $pythonExe (Join-Path $scriptDir "runtime\environment_manager.py") system-dependencies --group voice | ConvertFrom-Json
    foreach ($tool in $voicePrerequisites.tools) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            Write-Warning "Optional voice capability needs '$tool'. Install it separately to enable media decoding."
        }
    }
}

$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
$manager = Join-Path $scriptDir "runtime\environment_manager.py"
$setupStage = "python-environment"
& $pythonExe $manager record-step python-environment started
& $pythonExe $manager prepare-venv --python $pythonExe --path (Join-Path $scriptDir ".venv") | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Could not prepare a compatible Python environment. The previous environment was preserved; resolve the reported issue and rerun." }
& $pythonExe $manager record-step python-environment complete --detail $venvPython
& $venvPython -m pip install --upgrade pip
& $pythonExe $manager record-step python-dependencies started
$setupStage = "python-dependencies"
$dependencyArgs = @()
foreach ($group in $installGroups) {
    $resolved = & $venvPython (Join-Path $scriptDir "runtime\environment_manager.py") resolve-dependencies --group $group --format requirements
    if ($LASTEXITCODE -ne 0) { throw "Could not resolve dependency group '$group'." }
    $dependencyArgs += @($resolved | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}
$readyArgs = @()
foreach ($group in $installGroups) { $readyArgs += @("--group", $group) }
& $venvPython $manager dependencies-ready @readyArgs *> $null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Selected dependency groups already satisfy the compatibility manifest; resuming after that stage."
} else {
    & $venvPython -m pip install @dependencyArgs
    if ($LASTEXITCODE -ne 0) {
        & $pythonExe $manager record-step python-dependencies blocked --detail "Package installation failed; retry after resolving the package issue." | Out-Null
        & $pythonExe $manager restore-venv --path (Join-Path $scriptDir ".venv") | Out-Null
        throw "Dependency installation failed. The previous environment was restored when available and the failed candidate retained; rerun after resolving the package issue."
    }
}
if ($installGroups -contains "vision") { & $venvPython -m playwright install chromium }
& $pythonExe $manager record-step python-dependencies complete

$samData = Join-Path $env:USERPROFILE ".sam_data"
$setupStage = "ollama-start"
New-Item -ItemType Directory -Force -Path "$samData\logs", "$samData\memory\chroma", "$samData\founder_mode\export", "$samData\skills\compiled" | Out-Null

& $pythonExe $manager record-step ollama-start started
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
    $answer = Read-Host "Ollama is required for local models. Install it using the official installer now? [y/N]"
    if ($answer -notmatch '^[Yy]$') { throw "Install Ollama and rerun setup_windows.ps1." }
    $installerPath = Join-Path $env:TEMP "OllamaSetup.exe"
    Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $installerPath
    Start-Process -FilePath $installerPath -Wait
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) { throw "Ollama installer completed but ollama was not found on PATH. Restart PowerShell and rerun." }
}

$ready = $false
try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null; $ready = $true } catch {}
if (-not $ready) { Start-Process -FilePath $ollama.Source -ArgumentList "serve" -WindowStyle Hidden }
for ($i = 0; $i -lt 60 -and -not $ready; $i++) {
    Start-Sleep -Seconds 1
    try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null; $ready = $true } catch {}
}
if (-not $ready) { throw "Ollama did not become ready within 60 seconds." }
& $pythonExe $manager record-step ollama-start complete

$models = & $venvPython -c "from config.settings import Settings; s=Settings(); print('\n'.join(x or '' for x in (s.primary_model,s.fallback_model,s.embedding_model,s.vision_model)))"
$setupStage = "model-downloads"
$driveName = $env:USERPROFILE.Substring(0, 1)
$freeModelGb = [math]::Round((Get-PSDrive -Name $driveName).Free / 1GB, 1)
Write-Host "Available home-volume space before model downloads: $freeModelGb GB. Ollama reports exact progress after you select a model."
& $pythonExe $manager record-step model-downloads started --detail "Downloads require per-model confirmation"
foreach ($model in $models) {
    if ([string]::IsNullOrWhiteSpace($model)) { continue }
    $installedNames = @(& $ollama.Source list 2>$null | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] })
    if ($installedNames -contains $model) { Write-Host "Already installed: $model"; continue }
    $answer = Read-Host "Download '$model'? This may require several GB. [y/N]"
    if ($answer -match '^[Yy]$') { & $ollama.Source pull $model; if ($LASTEXITCODE -ne 0) { throw "Model download failed: $model" } }
    else { Write-Host "Skipped $model; downloads can be started later in SAM Settings." }
}
& $pythonExe $manager record-step model-downloads complete

Push-Location (Join-Path $scriptDir "interfaces\desktop")
$setupStage = "desktop-build"
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    npm run tauri -- build --bundles msi
    if ($LASTEXITCODE -ne 0) { throw "Tauri MSI build failed." }
} finally { Pop-Location }

$runtimeConfig = Join-Path $samData "desktop-runtime.json"
$setupStage = "runtime-configuration"
$existing = @{}
if (Test-Path $runtimeConfig) {
    $previous = Get-Content $runtimeConfig -Raw | ConvertFrom-Json
    foreach ($property in $previous.PSObject.Properties) { $existing[$property.Name] = $property.Value }
}
$apiPort = & $venvPython -c "from config.settings import Settings; print(Settings().api_port)"
$existing["environment_path"] = $env:PATH
$existing["app_root"] = $scriptDir
$existing["resources_dir"] = $scriptDir
$existing["sam_cli"] = Join-Path $scriptDir "sam_cli.py"
$existing["python"] = $venvPython
if (-not $existing.ContainsKey("api_base_url")) { $existing["api_base_url"] = "http://127.0.0.1:$apiPort" }
$runtimeJson = $existing | ConvertTo-Json -Depth 5
$temporaryConfig = "$runtimeConfig.tmp"
[System.IO.File]::WriteAllText($temporaryConfig, $runtimeJson, [System.Text.UTF8Encoding]::new($false))
if (Test-Path $runtimeConfig) { [System.IO.File]::Replace($temporaryConfig, $runtimeConfig, $null) }
else { [System.IO.File]::Move($temporaryConfig, $runtimeConfig) }

$legacyTask = Get-ScheduledTask -TaskName "SAM-Assistant" -ErrorAction SilentlyContinue
if ($legacyTask) {
    if ($legacyTask.State -eq "Running") {
        Stop-ScheduledTask -TaskName "SAM-Assistant"
        Start-Sleep -Seconds 2
        $legacyTask = Get-ScheduledTask -TaskName "SAM-Assistant"
        if ($legacyTask.State -eq "Running") { throw "The legacy SAM-Assistant task is still running; refusing to start a second backend manager." }
    }
    Disable-ScheduledTask -TaskName "SAM-Assistant" | Out-Null
    Write-Host "Disabled the legacy SAM-Assistant scheduled task; the desktop app now owns backend startup. The task was preserved."
}

$msi = Get-ChildItem (Join-Path $scriptDir "interfaces\desktop\src-tauri\target\release\bundle\msi") -Filter *.msi | Select-Object -First 1
if (-not $msi) { throw "Build succeeded but the MSI was not found." }
Write-Host "Installing the SAM desktop app from $($msi.FullName)"
Start-Process msiexec.exe -Verb RunAs -ArgumentList ('/i "{0}"' -f $msi.FullName) -Wait
Write-Host "Setup complete. Launch SAM from the Start menu; the desktop app owns the API process lifecycle."
