# Rollback

所有安装器使用版本化 `releases/`，并保留 `token`、`state`、`workspace`、`backups` 和旧 release。

- macOS：`./deploy/macos/uninstall.sh "$HOME/.wechat-codex-bridge"`
- Windows：`.\deploy\windows\Uninstall-WeChatCodexBridge.ps1`
- Linux：`./deploy/linux/uninstall.sh "$HOME/.wechat-codex-bridge"`

卸载只停止并归档本 Bridge 的服务元数据与 current 指针，不删除状态。机器人 AI 设置需使用 `wechat-codex-bridge-admin rollback BACKUP --apply` 从安装时生成的私有备份恢复。

回滚不会停止、删除或重建微信机器人及其他 AI 服务。
