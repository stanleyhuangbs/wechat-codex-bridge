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
| Windows | Contract-tested | Python 单元合同与 PowerShell 当前用户 ACL/计划任务资产已加入；本轮没有可达的已批准 Windows 主机，原生 Codex 登录、Docker 和微信仍需现场验证 |
| Linux | Contract-tested | Python 3.11 wheel、systemd user 和私网 gateway 合同已加入；本机 Docker Desktop 无法启动任何新建的 Linux 测试容器，已回收专用容器/网络，因此没有把该次尝试记为 Docker-verified |

### 环境记录（不含身份与网络信息）

- macOS：2026-08-24，arm64，Codex CLI 0.144.1，ChatGPT 登录可用，Docker 可用，最高 WeChat-verified。
- Windows：2026-08-24，当前无可达测试主机；版本、架构、Codex 登录和 Docker 均未验证，最高 Contract-tested。
- Linux：2026-08-24，计划使用 Python 3.11 arm64 官方容器；镜像存在但 Docker 后端把最小新容器停在 Created，未得到运行时版本或请求证据，最高 Contract-tested。

首发前会继续提升 Windows/Linux 能取得的证据等级；无法取得时保持当前标记，不用 CI 代替。
