# WeChat Codex Bridge

把本机 Docker 微信机器人连接到宿主机当前已经登录的 Codex CLI 账号。Bridge 在宿主机以当前用户运行，按匿名微信会话持续恢复 Codex thread，并向机器人提供带 Bearer 鉴权的 OpenAI-compatible 接口。

## 三个独立项目

- [`stanleyhuangbs/wechat-robot-client-local`](https://github.com/stanleyhuangbs/wechat-robot-client-local)：真正的微信机器人，负责微信登录、收发消息、下载图片/语音/视频/文件以及回发。
- 本仓库 `wechat-codex-bridge`：让该机器人使用当前系统登录的 Codex，支持持续对话、图片与视频帧、可选本地 Whisper 语音转写。
- 可选的 [`stanleyhuangbs/wechat-agent-bridge`](https://github.com/stanleyhuangbs/wechat-agent-bridge)：用于私有附件归档、文档提取、CLI/MCP 转交。`wechat-agent-bridge` 不是必装，也不是微信机器人本体。

只安装微信机器人时，原有图片、语音、视频、文件收发能力仍然存在；只有需要“微信直接使用当前 Codex 登录”时才安装本 Bridge。

## 安全默认值

- 不读取、复制或打包 Codex 的认证文件，只让 Codex CLI 在当前用户环境中自行使用已有登录。
- Codex 运行在 read-only sandbox，禁用 Shell、浏览器、插件和外部操作工具。
- macOS/Windows 只绑定 loopback；Linux 只绑定已验证的目标 Docker 私网 gateway，拒绝 `0.0.0.0`。
- token、会话目录和备份仅当前用户可读；安装、升级、卸载不删除状态与旧 release。

## 支持状态

| 系统 | 当前证据 |
|---|---|
| macOS | WeChat-verified（文字持续会话）；Docker-verified（大图、6 视频帧）；本地语音转写已验证 |
| Windows | Contract-tested；GitHub Windows runner 已完成测试、构建、干净安装、CLI 冒烟和 PowerShell 解析；真实 Codex 登录、Docker 与微信仍待现场验证 |
| Linux | Contract-tested；GitHub Ubuntu runner 已完成测试、构建、干净安装和 CLI 冒烟，Docker gateway 合同已验证；真实宿主 Codex/Docker/微信仍待现场验证 |

安装前先阅读 [安装说明](docs/installation.md)、[安全边界](SECURITY.md) 和 [回滚说明](docs/rollback.md)。架构细节见 [architecture](docs/architecture.md)。
