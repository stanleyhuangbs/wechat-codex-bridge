# Security

## 边界

Bridge 只接受带私有 Bearer token 的 `/healthz`、`/v1/chat/completions` 和可选 `/transcribe`。它不提供 Shell、通用文件读取、任意 URL 抓取或账号导出接口。

不要把 token、Codex 认证目录、会话目录、微信数据库、备份或运行日志提交到 Git。不要绑定 `0.0.0.0`，也不要把端口直接暴露到公网。

Codex 子进程继承当前用户的登录环境，但环境变量经过白名单过滤；Bridge 不打开或复制认证文件。会话 scope 只保存 SHA-256 摘要。

## 报告问题

请通过 GitHub Security Advisory 私下报告鉴权绕过、路径逃逸、秘密泄漏或远程执行问题。报告中不要附真实 token、微信 ID、会话正文或认证文件。
