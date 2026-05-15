# ============================================================
# knowledge-base 试用版安装脚本 (PowerShell)
#
# 用法:右键本文件选 "Run with PowerShell",或在 PS 窗口跑 .\install.ps1
# 等价的 Batch 版:install.bat(行为完全一致,选哪个都行)
#
# 如果 PowerShell 提示 "执行策略" 错误(脚本被禁止执行),两个解决办法:
#   A) 在 PS 窗口跑:Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
#   B) 改用 install.bat 双击(更简单,推荐不会改 PS 策略的用户)
# ============================================================

# 不用 ErrorActionPreference=Stop:对原生命令 (pip/python) 太敏感,会把 stderr 当致命错误。
# 改为显式检查 $LASTEXITCODE,cmdlet 失败用 try/catch。

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Set-Location -Path $PSScriptRoot

Write-Host "=== knowledge-base 试用版安装脚本 (install.ps1) ==="
Write-Host ""

# ---------- [1/6] Python 版本 ----------
Write-Host "[1/6] 检查 Python 版本(必须 3.10-3.12)..."
$pyOutput = $null
try {
    $pyOutput = & python --version
} catch {
    $pyOutput = $null
}
if (-not $pyOutput -or $LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] 未检测到 Python" -ForegroundColor Red
    Write-Host "    请装 Python 3.10-3.12,下载:https://www.python.org/downloads/"
    Write-Host "    装好后勾选 'Add Python to PATH',重开 PowerShell 重试。"
    exit 1
}
$verstr = ($pyOutput -replace 'Python ', '').Trim()
try {
    $ver = [version]$verstr
} catch {
    Write-Host "  [FAIL] 解析 Python 版本失败:$verstr" -ForegroundColor Red
    exit 1
}
if ($ver -lt [version]'3.10' -or $ver -ge [version]'3.13') {
    Write-Host "  [FAIL] Python 版本不在 3.10-3.12 范围(检测到 $verstr)" -ForegroundColor Red
    Write-Host "    请装 Python 3.10-3.12,下载:https://www.python.org/downloads/"
    exit 1
}
Write-Host "  [OK] Python $verstr 满足要求" -ForegroundColor Green
Write-Host ""

# ---------- [2/6] tools/rg.exe ----------
Write-Host "[2/6] 检查 tools/rg.exe..."
$rgPath = Join-Path $PSScriptRoot "tools\rg.exe"
if (-not (Test-Path $rgPath)) {
    Write-Host "  [FAIL] tools/rg.exe 缺失" -ForegroundColor Red
    Write-Host "    仓库不完整,请重新下载完整仓库或检查 zip 是否完全解压。"
    exit 1
}
$rgVerLine = (& $rgPath --version) | Select-Object -First 1
if ($LASTEXITCODE -ne 0 -or -not $rgVerLine) {
    Write-Host "  [FAIL] tools/rg.exe 存在但跑不起来" -ForegroundColor Red
    Write-Host "    可能文件损坏,请重新下载完整仓库。"
    exit 1
}
$rgVer = ($rgVerLine -split '\s+')[1]
Write-Host "  [OK] tools/rg.exe 就位(版本 $rgVer)" -ForegroundColor Green
Write-Host ""

# ---------- [3/6] venv ----------
Write-Host "[3/6] 创建虚拟环境 .venv..."
$venvPath = Join-Path $PSScriptRoot ".venv"
if (Test-Path $venvPath) {
    Write-Host "  [WARN] .venv 已存在,跳过创建(若想重建,先手动删除 .venv 目录)" -ForegroundColor Yellow
} else {
    & python -m venv .venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] python -m venv .venv 失败(见上方报错)" -ForegroundColor Red
        Write-Host "    检查 Python 安装是否完整(标准 Python 自带 venv 模块,精简包可能缺失)。"
        exit 1
    }
    Write-Host "  [OK] .venv 已创建" -ForegroundColor Green
}
Write-Host ""

# ---------- [4/6] pip install ----------
Write-Host "[4/6] 安装依赖(可能需要几分钟,请耐心等待)..."
& .venv\Scripts\pip.exe install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [WARN] 首次 pip install 失败,自动用清华镜像重试一次..." -ForegroundColor Yellow
    & .venv\Scripts\pip.exe install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  [FAIL] pip install 重试仍失败(见上方报错)" -ForegroundColor Red
        Write-Host "    常见处理:"
        Write-Host "      权限问题  - 关闭 PowerShell,右键以管理员身份重新打开,再跑 install.ps1"
        Write-Host "      SSL 问题  - 先升级 pip:.venv\Scripts\python.exe -m pip install --upgrade pip"
        Write-Host "      代理问题  - 配置 pip 走公司代理:`$env:HTTPS_PROXY='http://your.proxy:port',再跑 install.ps1"
        exit 1
    }
    Write-Host "  [OK] 镜像重试成功" -ForegroundColor Green
}
$pkgList = & .venv\Scripts\pip.exe list --format=freeze
$pkgCount = ($pkgList | Measure-Object -Line).Lines
Write-Host "  [OK] 依赖安装完成($pkgCount 个包)" -ForegroundColor Green
Write-Host ""

# ---------- [5/6] 验证 ----------
Write-Host "[5/6] 验证安装(跑 search.py 烟测查询)..."
& .venv\Scripts\python.exe scripts\search.py --scene all --terms "__install_smoke_test_zzzz__" | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [FAIL] 验证步骤异常(search.py 烟测失败)" -ForegroundColor Red
    Write-Host "    安装可能不完整。手动跑一次看错误:.venv\Scripts\python.exe scripts\search.py --scene all --terms test"
    Write-Host "    仍解决不了请联系维护者。"
    exit 1
}
Write-Host "  [OK] 验证通过" -ForegroundColor Green
Write-Host ""

# ---------- [6/6] 完成 ----------
Write-Host "[6/6] 安装完成。请阅读 docs/试用指南.md 开始使用。" -ForegroundColor Green
exit 0
