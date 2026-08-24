#!/bin/sh
set -eu
[ "$#" -eq 1 ] || exit 2
runtime_root=$1; case "$runtime_root" in /*) ;; *) exit 2;; esac
stamp=$(date -u +%Y%m%dT%H%M%SZ); recovery="$runtime_root/recovery/uninstall-$stamp"
mkdir -p "$recovery"; chmod 700 "$recovery"
plist="$HOME/Library/LaunchAgents/ai.wechat-codex-bridge.plist"
launchctl bootout "gui/$(id -u)/ai.wechat-codex-bridge" 2>/dev/null || true
[ ! -e "$plist" ] || mv "$plist" "$recovery/"
[ ! -e "$runtime_root/current" ] || mv "$runtime_root/current" "$recovery/current-release-link"
echo "preserved: token state releases backups workspace; recovery=$recovery"
