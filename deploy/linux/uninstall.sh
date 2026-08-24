#!/bin/sh
set -eu
[ "$#" -eq 1 ] || exit 2
runtime_root=$1; stamp=$(date -u +%Y%m%dT%H%M%SZ); recovery="$runtime_root/recovery/uninstall-$stamp"
mkdir -p "$recovery"; chmod 700 "$recovery"
systemctl --user disable --now wechat-codex-bridge.service 2>/dev/null || true
service="$HOME/.config/systemd/user/wechat-codex-bridge.service"; [ ! -e "$service" ] || mv "$service" "$recovery/"
[ ! -e "$runtime_root/current" ] || mv "$runtime_root/current" "$recovery/current-release-link"
systemctl --user daemon-reload
echo "preserved: token state releases backups workspace; recovery=$recovery"
