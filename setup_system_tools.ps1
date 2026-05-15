# ============================================================
# setup_system_tools.ps1 - System tools detection guide (v0.7)
#
# Purpose: Detect rg / ffmpeg / poppler; print install hints on miss;
#          honest soft-degradation (does NOT block main flow).
#
# Usage:   Right-click -> "Run with PowerShell", or .\setup_system_tools.ps1
# Batch:   setup_system_tools.bat (equivalent)
#
# Relation to install.bat: INDEPENDENT, NOT auto-chained.
#   - install: Python venv + pip + bundled rg.exe + smoke test
#   - this:    system tools detection; skip entirely if you only use text materials
# ============================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location -Path $PSScriptRoot

Write-Host "=== System tools detection guide (setup_system_tools.ps1) ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Detects 3 optional system tools (rg / ffmpeg / poppler)."
Write-Host "Missing tools print install hints; this script does NOT block main flow."
Write-Host ""

$missing = @()

# ---------- [1/3] system rg (optional; repo ships tools/rg.exe) ----------
Write-Host "[1/3] Detecting system ripgrep (rg)..."
$rgFound = $null
try { $rgFound = & rg --version 2>$null | Select-Object -First 1 } catch {}
if ($rgFound) {
    Write-Host "  [OK]   system rg installed: $rgFound" -ForegroundColor Green
} else {
    Write-Host "  [INFO] system rg not detected" -ForegroundColor Yellow
    Write-Host "         Impact: NONE; repo ships tools/rg.exe; scripts/search.py prefers bundled."
    Write-Host "         Install (recommended order):"
    Write-Host "           1. winget install BurntSushi.ripgrep.MSVC"
    Write-Host "           2. choco install ripgrep"
    Write-Host "           3. Manual: https://github.com/BurntSushi/ripgrep/releases"
    $missing += "rg (optional; repo bundles tools/rg.exe)"
}
Write-Host ""

# ---------- [2/3] ffmpeg (optional; video frame extraction) ----------
Write-Host "[2/3] Detecting ffmpeg..."
$ffmpegFound = $null
try { $ffmpegFound = & ffmpeg -version 2>$null | Select-Object -First 1 } catch {}
if ($ffmpegFound) {
    Write-Host "  [OK]   ffmpeg installed: $ffmpegFound" -ForegroundColor Green
} else {
    Write-Host "  [WARN] ffmpeg not detected" -ForegroundColor Yellow
    Write-Host "         Impact: video frame extraction (path B, V3/V4 fixtures) disabled."
    Write-Host "                 Image-heavy path (path A) NOT affected."
    Write-Host "         Install (recommended order):"
    Write-Host "           1. winget install Gyan.FFmpeg"
    Write-Host "           2. choco install ffmpeg"
    Write-Host "           3. Manual: https://www.gyan.dev/ffmpeg/builds/  (add to PATH after extract)"
    $missing += "ffmpeg (video frame extraction)"
}
Write-Host ""

# ---------- [3/3] poppler / pdftoppm (optional; scanned PDF rendering) ----------
Write-Host "[3/3] Detecting poppler (pdftoppm)..."
$popplerFound = $null
try { $popplerFound = & pdftoppm -v 2>&1 | Select-Object -First 1 } catch {}
if ($popplerFound -and ($popplerFound -match "pdftoppm")) {
    Write-Host "  [OK]   poppler installed: $popplerFound" -ForegroundColor Green
} else {
    Write-Host "  [WARN] poppler / pdftoppm not detected" -ForegroundColor Yellow
    Write-Host "         Impact: scanned PDF vision path disabled;"
    Write-Host "                 scanned PDF falls back to L3 stub (vision_status: failed_no_pdf_converter)."
    Write-Host "         Install (recommended order):"
    Write-Host "           1. winget install oschwartz10612.Poppler"
    Write-Host "           2. choco install poppler"
    Write-Host "           3. Manual: https://github.com/oschwartz10612/poppler-windows/releases"
    Write-Host "              (add bin/ to PATH after extract)"
    $missing += "poppler (scanned PDF rendering)"
}
Write-Host ""

# ---------- Summary ----------
if ($missing.Count -eq 0) {
    Write-Host "=== All 3 system tools installed ===" -ForegroundColor Green
} else {
    Write-Host "=== Detection complete. Missing tools (install on demand; main flow NOT blocked) ===" -ForegroundColor Yellow
    foreach ($m in $missing) {
        Write-Host "  - $m"
    }
    Write-Host ""
    Write-Host "If you only use text materials (.md / .txt / .docx etc.), skip all of these."
    Write-Host "winget not installed (common on Win10 LTSC 2021)?"
    Write-Host "  Install winget, use chocolatey, or download binaries manually (links above)."
}

Write-Host ""
Write-Host "[INFO] setup_system_tools done. Re-run after installing to verify." -ForegroundColor Cyan
exit 0
