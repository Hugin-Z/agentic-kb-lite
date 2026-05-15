#!/usr/bin/env bash
# ============================================================
# setup_system_tools.sh — 系统工具检测引导(macOS / Linux best effort)
# v0.7 引入。Windows 主版本是 setup_system_tools.bat / .ps1
#
# 用途:检测 rg / ffmpeg / poppler 三个系统工具是否安装,
#       给出 brew / apt 安装命令 + 失败软降级语义,不阻塞主流程。
# ============================================================

set -u

echo "=== 系统工具检测引导(setup_system_tools.sh)==="
echo
echo "本脚本检测 3 个系统工具(rg / ffmpeg / poppler),"
echo "缺失时给出安装提示,**不阻塞主流程**(沿用诚实降级红线)。"
echo

# 检测平台 + 给出对应包管理器命令
PLATFORM="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
    PLATFORM="macOS"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    PLATFORM="Linux"
fi

missing=()

check_tool() {
    local name="$1"
    local cmd="$2"
    local desc="$3"
    local brew_pkg="$4"
    local apt_pkg="$5"
    local fallback_url="$6"

    if command -v "$cmd" >/dev/null 2>&1; then
        local ver
        ver=$("$cmd" --version 2>/dev/null | head -1)
        echo "  [OK]  $name 已装($ver)"
    else
        echo "  [WARN] $name 未检测到"
        echo "         影响:$desc"
        echo "         安装(推荐顺序):"
        if [[ "$PLATFORM" == "macOS" ]]; then
            echo "           1. brew install $brew_pkg"
        elif [[ "$PLATFORM" == "Linux" ]]; then
            echo "           1. sudo apt install $apt_pkg  (Debian/Ubuntu)"
            echo "              sudo dnf install $apt_pkg  (Fedora/RHEL)"
        fi
        echo "           2. 手动下载: $fallback_url"
        missing+=("$name")
    fi
    echo
}

echo "[1/3] 检测系统 ripgrep(rg)..."
check_tool "rg" "rg" \
    "无;**仓库已自带 tools/rg.exe**(Windows),Unix 系统建议装系统 rg" \
    "ripgrep" "ripgrep" \
    "https://github.com/BurntSushi/ripgrep/releases"

echo "[2/3] 检测 ffmpeg..."
check_tool "ffmpeg" "ffmpeg" \
    "**视频抽帧(路径 B,V3/V4)失效**;图为主(路径 A)不受影响" \
    "ffmpeg" "ffmpeg" \
    "https://www.gyan.dev/ffmpeg/builds/"

echo "[3/3] 检测 poppler(pdftoppm)..."
check_tool "poppler" "pdftoppm" \
    "**扫描 PDF 走 vision 失效**;降级到 L3 stub 兜底(vision_status: failed_no_pdf_converter)" \
    "poppler" "poppler-utils" \
    "https://poppler.freedesktop.org/"

if [[ ${#missing[@]} -eq 0 ]]; then
    echo "=== 全部 3 个系统工具已就位 ==="
else
    echo "=== 完成检测;以下工具未装(可按需安装,不阻塞主流程)==="
    for m in "${missing[@]}"; do
        echo "  - $m"
    done
    echo
    echo "若你**只用文本类素材**(.md / .txt / .docx 等),可全部跳过。"
fi

echo
echo "[INFO] setup_system_tools 完成。装完工具后重跑本脚本验证。"
exit 0
