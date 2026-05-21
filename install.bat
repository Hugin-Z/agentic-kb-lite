@echo off
REM ============================================================
REM knowledge-base trial install (Batch, double-click ready)
REM
REM Usage: double-click in File Explorer, or run "install.bat" in cmd.
REM Equivalent PowerShell version: install.ps1 (same behavior).
REM
REM Note: this .bat is ASCII-only by design (Windows bat parser is
REM brittle with Chinese encoding). The companion install.ps1 has
REM Chinese messages if you prefer that.
REM ============================================================

setlocal enabledelayedexpansion
cd /d "%~dp0"

echo === knowledge-base trial install (install.bat) ===
echo.

REM ---------- [1/6] Python version (must be 3.10-3.12) ----------
echo [1/6] Checking Python version (must be 3.10-3.12)...
where python >nul 2>&1
if errorlevel 1 goto :err_python_missing
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo %PYVER% | findstr /R "^3\.1[012]\." >nul
if errorlevel 1 goto :err_python_version
echo   [OK] Python %PYVER% meets requirement
echo.

REM ---------- [2/6] tools/rg.exe ----------
echo [2/6] Checking tools/rg.exe...
if not exist "tools\rg.exe" goto :err_rg_missing
for /f "tokens=2" %%v in ('tools\rg.exe --version ^| findstr /B "ripgrep"') do set RGVER=%%v
echo   [OK] tools/rg.exe present (version %RGVER%)
echo.

REM ---------- [3/6] venv ----------
echo [3/6] Creating virtualenv .venv...
if exist ".venv" (
    echo   [WARN] .venv already exists, skip create. To rebuild, delete .venv first.
) else (
    python -m venv .venv
    if errorlevel 1 goto :err_venv
    echo   [OK] .venv created
)
echo.

REM ---------- [4/6] pip install ----------
echo [4/6] Installing dependencies (may take a few minutes)...
.venv\Scripts\pip.exe install -r requirements.txt
if not errorlevel 1 goto :pip_ok
echo   [WARN] First pip install failed, retrying with CN mirror...
.venv\Scripts\pip.exe install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 goto :err_pip
echo   [OK] mirror retry succeeded
:pip_ok
for /f %%c in ('.venv\Scripts\pip.exe list --format^=freeze ^| find /c /v ""') do set PKGCNT=%%c
echo   [OK] dependencies installed (%PKGCNT% packages)
echo.

REM ---------- [5/6] verify ----------
echo [5/6] Verifying install (smoke test on search.py)...
.venv\Scripts\python.exe scripts\search.py --scope all --terms "__install_smoke_test_zzzz__" >nul 2>&1
if errorlevel 1 goto :err_verify
echo   [OK] verification passed
echo.

REM ---------- [6/6] done ----------
echo [6/6] Install complete. Please read README.md to start.
exit /b 0


REM ============== error handlers ==============

:err_python_missing
echo   [FAIL] Python not detected on PATH
echo     Install Python 3.10-3.12: https://www.python.org/downloads/
echo     During install, check "Add Python to PATH". Reopen cmd and retry.
exit /b 1

:err_python_version
echo   [FAIL] Python version not in 3.10-3.12 (detected %PYVER%)
echo     Install Python 3.10-3.12: https://www.python.org/downloads/
exit /b 1

:err_rg_missing
echo   [FAIL] tools/rg.exe missing
echo     Repository incomplete. Re-download the full repo or check your zip extraction.
exit /b 1

:err_venv
echo   [FAIL] python -m venv .venv failed (see error above)
echo     Check Python install integrity (standard Python ships with venv module).
exit /b 1

:err_pip
echo   [FAIL] pip install retry also failed (see error above)
echo     Common fixes:
echo       Permission  - close cmd, right-click "Run as administrator", re-run install.bat
echo       SSL  - upgrade pip first: .venv\Scripts\python.exe -m pip install --upgrade pip
echo       Proxy  - set HTTPS_PROXY=http://your.proxy:port, then re-run install.bat
exit /b 1

:err_verify
echo   [FAIL] verification step failed (search.py smoke test)
echo     Install may be incomplete. Manual debug: .venv\Scripts\python.exe scripts\search.py --scope all --terms test
echo     If still failing, contact the maintainer.
exit /b 1
