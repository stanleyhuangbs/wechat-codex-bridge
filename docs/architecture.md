# Architecture

```text
WeChat user
    ↓
wechat-robot-client-local (Docker)
    ↓ Bearer + stable anonymous scope
wechat-codex-bridge (host current user)
    ↓ codex exec / resume
current Codex login
```

机器人负责微信协议、媒体下载、文档提取和消息回发。Bridge 负责鉴权、请求限额、scope 互斥、持续 thread、Codex read-only 调用和最终文本响应。

图片以 data URL 传入，最多 8 张；机器人视频默认抽取最多 6 帧。语音和视频音轨可交给本机 Whisper CLI。PDF/Office 等文档由机器人容器先提取为不可信文本，再交给 Codex；不要求安装附件桥。

macOS/Windows Docker Desktop 使用 `host.docker.internal`。Linux 使用目标容器所属网络的精确私有 gateway，服务不绑定通配地址。
