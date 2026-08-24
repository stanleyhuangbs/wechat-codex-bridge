# Verification

## 证据等级

| 等级 | 含义 |
|---|---|
| Contract-tested | 单元、包、安装器和模拟命令通过 |
| Host-verified | 该系统当前 Codex 登录完成 fresh/resume |
| Docker-verified | Docker 容器完成真实带鉴权请求 |
| WeChat-verified | 手机端微信入站、可见回复和同会话恢复通过 |

CI 不等于真实 Codex 登录，也不等于 Docker 或手机端微信验收。

## 2026-08-24 证据

| 系统 | 等级 | 说明 |
|---|---|---|
| macOS | WeChat-verified | 文字两轮持续会话在手机端可见；Docker 大于旧 128KB 的图片和 6 视频帧请求均返回 200；同 token Whisper 合成语音返回 200 |
| Windows | Contract-tested | GitHub Windows runner 已完成单元测试、编译、wheel 构建、干净安装、两个 CLI 冒烟、公共包扫描和 PowerShell 安装器解析；原生 Codex 登录、Docker 和微信仍需现场验证 |
| Linux | Contract-tested | GitHub Ubuntu runner 已完成单元测试、编译、wheel 构建、干净安装、两个 CLI 冒烟和公共包扫描；systemd user 与私网 gateway 合同已验证，真实宿主 Codex/Docker/微信仍需现场验证 |

### 环境记录（不含身份与网络信息）

- macOS：2026-08-24，arm64，Codex CLI 0.144.1，ChatGPT 登录可用，Docker 可用，最高 WeChat-verified。
- Windows：2026-08-24，GitHub `windows-latest` + Python 3.11 托管验证通过；没有用户批准的真实账号主机，Codex 登录、Docker 和微信均未验证，最高 Contract-tested。
- Linux：2026-08-24，GitHub `ubuntu-latest` + Python 3.11 托管验证通过；此前本机 Docker Desktop 把最小新容器停在 Created，未取得真实宿主 Codex、Docker Bridge 请求或微信证据，最高 Contract-tested。

三平台托管验证记录：[GitHub Actions run 32717601111](https://github.com/stanleyhuangbs/wechat-codex-bridge/actions/runs/32717601111)。后续只有取得真实账号与微信端到端证据才提升 Windows/Linux 等级，不用 CI 代替运行时验收。
