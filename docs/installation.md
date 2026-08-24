# Installation

## 前置条件

- 已安装并登录 Codex CLI，终端运行 `codex login status` 可确认当前账号状态。
- 已运行唯一一个 `client_*` Docker 微信机器人。
- Python 3.11+；需要语音时另外安装可执行的 Whisper CLI。

## macOS

```sh
./deploy/macos/install.sh "$PWD" "$HOME/.wechat-codex-bridge"
"$HOME/.wechat-codex-bridge/current/venv/bin/wechat-codex-bridge-admin" configure \
  --token-path "$HOME/.wechat-codex-bridge/token" --apply
```

Docker 通过 `http://host.docker.internal:18791` 访问 Bridge。

## Windows PowerShell

```powershell
.\deploy\windows\Install-WeChatCodexBridge.ps1 -SourceRoot $PWD
wechat-codex-bridge-admin configure --token-path "$env:LOCALAPPDATA\WeChatCodexBridge\token" --apply
```

安装器创建当前用户计划任务和当前用户 ACL，不使用系统账号。

## Linux

```sh
./deploy/linux/install.sh "$PWD" "$HOME/.wechat-codex-bridge"
"$HOME/.wechat-codex-bridge/current/venv/bin/wechat-codex-bridge-admin" configure \
  --token-path "$HOME/.wechat-codex-bridge/token" --apply
```

安装器发现唯一目标容器的 Docker 私网 gateway，以 systemd user service 启动。若目标不唯一或 gateway 不安全，安装会停止。

配置命令默认 dry-run；只有显式 `--apply` 才会先备份并更新唯一的全局 AI 设置行。
