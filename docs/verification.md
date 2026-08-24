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
| Windows | Contract-tested | Python 与 PowerShell 安装合同已加入；原生 Codex 登录、Docker 和微信仍需现场验证 |
| Linux | Contract-tested | Python、systemd user、私网 gateway 合同已加入；真实登录与 Docker 请求仍需现场验证 |

首发前会继续提升 Windows/Linux 能取得的证据等级；无法取得时保持当前标记，不用 CI 代替。
