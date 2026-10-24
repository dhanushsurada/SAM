<#
 SAM installer for Windows — downloads the latest release from GitHub,
 verifies its SHA-256 checksum, and runs the installer.

   irm https://raw.githubusercontent.com/dhanushsurada/SAM/main/scripts/install.ps1 | iex

 Environment variables: SAM_VERSION (tag, default latest), SAM_REPO (owner/name).
#>
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$repo = if ($env:SAM_REPO) { $env:SAM_REPO } else { "dhanushsurada/SAM" }
$version = if ($env:SAM_VERSION) { $env:SAM_VERSION } else { "latest" }
$url = if ($version -eq "latest") { "https://api.github.com/repos/$repo/releases/latest" } else { "https://api.github.com/repos/$repo/releases/tags/$version" }

if (-not [Environment]::Is64BitOperatingSystem) { throw "SAM requires 64-bit Windows 10 or later." }
Write-Host "==> Looking up release ($version) from github.com/$repo"
try { $release = Invoke-RestMethod -Uri $url -Headers @{ Accept = "application/vnd.github+json" } }
catch { throw "Could not read release information. Is there a published release yet? $($_.Exception.Message)" }

$asset = $release.assets | Where-Object { $_.name -match '^SAM_.*_windows-x86_64-setup\.exe$' } | Select-Object -First 1
$sums  = $release.assets | Where-Object { $_.name -eq "SHA256SUMS.txt" } | Select-Object -First 1
if (-not $asset) { throw "No Windows installer found in that release." }
if (-not $sums)  { throw "The release has no SHA256SUMS.txt; refusing to run an unverifiable installer." }

$dir = Join-Path $env:TEMP ("sam-install-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $dir | Out-Null
try {
    $file = Join-Path $dir $asset.name
    Write-Host "==> Downloading $($asset.name)"
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $file
    $sumsText = (Invoke-WebRequest -Uri $sums.browser_download_url).Content
    if ($sumsText -is [byte[]]) { $sumsText = [Text.Encoding]::UTF8.GetString($sumsText) }

    Write-Host "==> Verifying checksum"
    $line = ($sumsText -split "`n") | Where-Object { $_ -match [regex]::Escape($asset.name) } | Select-Object -First 1
    if (-not $line) { throw "Checksum for $($asset.name) is not listed in SHA256SUMS.txt." }
    $expected = ($line.Trim() -split '\s+')[0].ToLower()
    $actual = (Get-FileHash -Algorithm SHA256 -Path $file).Hash.ToLower()
    if ($expected -ne $actual) { throw "Checksum mismatch - the download is corrupt or tampered with. Nothing was installed." }

    Write-Host "==> Starting the SAM installer"
    Start-Process -FilePath $file -Wait
    Write-Host "Done. Launch SAM from the Start menu."
} finally {
    Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
}
