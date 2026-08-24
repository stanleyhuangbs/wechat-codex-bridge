# WeChat Codex Bridge

Connect a locally installed Docker WeChat robot to the Codex CLI account already signed in on the host. The Bridge runs on the host, keeps conversation scopes separate, and exposes a Bearer-authenticated OpenAI-compatible endpoint to the robot.

This is an independent companion to [`wechat-robot-client-local`](https://github.com/stanleyhuangbs/wechat-robot-client-local), not a replacement for the WeChat robot. The robot continues to handle WeChat login, messages, images, voice, video, files, and replies. This Bridge adds current-user Codex chat, bounded image/video-frame understanding, and optional local Whisper transcription through the same private token.

Users who additionally need private attachment archiving, document extraction, CLI, or MCP handoff can install the separate optional [`wechat-agent-bridge`](https://github.com/stanleyhuangbs/wechat-agent-bridge).

Platform installers and verified macOS, Windows, and Linux instructions are being finalized before the first public release.
