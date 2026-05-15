# tools/

本仓库自带的二进制工具,纳入 git 仓库随同分发(便于开箱即用)。

## tools/rg.exe — bundled ripgrep

| 项 | 值 |
|---|---|
| 工具 | ripgrep(rg) |
| 版本 | **15.1.0**(rev af60c2de9d,features:+pcre2)|
| 上游 | <https://github.com/BurntSushi/ripgrep> |
| 协议 | MIT License(详见 ripgrep 上游 [LICENSE-MIT](https://github.com/BurntSushi/ripgrep/blob/master/LICENSE-MIT))|
| 平台 | Windows x86_64 |

### 为何 bundle

`scripts/search.py` 的检索主入口需要 ripgrep。Windows 用户系统层装 rg 路径不固定(`winget install BurntSushi.ripgrep.MSVC` / `choco install ripgrep` / 手动下载),bundle 一份 `tools/rg.exe` 让试用者**开箱即用**,无需先装系统级 rg。

`scripts/search.py` 的 `resolve_rg_path()` 优先用 bundled,fallback 到系统 PATH 的 rg(详见 [scripts/README.md](../scripts/README.md))。

### 合法分发声明

ripgrep 采用 **MIT License**(及 Unlicense 双重许可),**允许 redistributing in binary form including for commercial purposes**。本仓库分发 `tools/rg.exe` 完全合法,无修改、无重打包,仅作为依赖工具捆绑。

完整 license 原文见 [`./LICENSE-ripgrep`](./LICENSE-ripgrep)(1081 字节,与上游 <https://github.com/BurntSushi/ripgrep/blob/master/LICENSE-MIT> 字节级一致)。

### 升级 rg.exe

1. 从 <https://github.com/BurntSushi/ripgrep/releases> 下载最新 Windows x86_64 zip
2. 替换 `tools/rg.exe`
3. 运行 `./tools/rg.exe --version` 确认新版本
4. 同步更新本文件的"版本"字段

### macOS / Linux 用户

`tools/rg.exe` 是 Windows 专用。macOS / Linux 用户请用系统包管理器装 rg:

```bash
brew install ripgrep        # macOS
sudo apt install ripgrep    # Debian / Ubuntu
sudo dnf install ripgrep    # Fedora / RHEL
```

跑 `setup_system_tools.sh` 可自动检测 + 给安装提示。
