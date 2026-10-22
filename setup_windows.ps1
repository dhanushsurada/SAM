# SAM Windows source-based developer setup.
# Builds the same Tauri desktop client as macOS; it does not install a
# separately supervised Python backend. Run from PowerShell in the checkout.
$ErrorActionPreference = "Stop"
$scriptDir = $PSScriptRoot
Set-Location $scriptDir

foreach ($tool in @("python", "node", "npm", "cargo")) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Missing $tool. Install Python 3, Node.js, and the Rust toolchain, then rerun setup_windows.ps1."
    }
}

$pythonExe = (Get-Command python).Source
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    if (Test-Path (Join-Path $scriptDir ".venv")) {
        throw "An incomplete .venv exists. Move it aside yourself; setup will not delete it."
    }
    & $pythonExe -m venv (Join-Path $scriptDir ".venv")
}
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $scriptDir "requirements.txt")
& $venvPython -m pip install pyttsx3 pywinauto
& $venvPython -m playwright install chromium

$samData = Join-Path $env:USERPROFILE ".sam_data"
New-Item -ItemType Directory -Force -Path "$samData\logs", "$samData\memory\chroma", "$samData\founder_mode\export", "$samData\skills\compiled" | Out-Null

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

$models = & $venvPython -c "from config.settings import Settings; s=Settings(); print('\n'.join(x or '' for x in (s.primary_model,s.fallback_model,s.embedding_model,s.vision_model)))"
foreach ($model in $models) {
    if ([string]::IsNullOrWhiteSpace($model)) { continue }
    $installedNames = @(& $ollama.Source list 2>$null | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] })
    if ($installedNames -contains $model) { Write-Host "Already installed: $model"; continue }
    $answer = Read-Host "Download '$model'? This may require several GB. [y/N]"
    if ($answer -match '^[Yy]$') { & $ollama.Source pull $model; if ($LASTEXITCODE -ne 0) { throw "Model download failed: $model" } }
    else { Write-Host "Skipped $model; downloads can be started later in SAM Settings." }
}

Push-Location (Join-Path $scriptDir "interfaces\desktop")
try {
    npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    npm run tauri -- build --bundles msi
    if ($LASTEXITCODE -ne 0) { throw "Tauri MSI build failed." }
} finally { Pop-Location }

$runtimeConfig = Join-Path $samData "desktop-runtime.json"
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
[System.IO.File]::WriteAllText($runtimeConfig, $runtimeJson, [System.Text.UTF8Encoding]::new($false))

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
