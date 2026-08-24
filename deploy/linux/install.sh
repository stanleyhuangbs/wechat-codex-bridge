#!/bin/sh
set -eu
[ "$#" -eq 2 ] || { echo "usage: install.sh SOURCE_ROOT RUNTIME_ROOT" >&2; exit 2; }
source_root=$1; runtime_root=$2; case "$source_root:$runtime_root" in /*:/*) ;; *) exit 2;; esac
python_bin=${PYTHON_BIN:-python3}; codex_bin=${CODEX_BIN:-$(command -v codex || true)}; [ -x "$codex_bin" ] || exit 2
stamp=$(date -u +%Y%m%dT%H%M%SZ); release="$runtime_root/releases/$stamp"
mkdir -p "$release/wheel" "$runtime_root/state" "$runtime_root/workspace" "$runtime_root/recovery" "$HOME/.config/systemd/user"
chmod 700 "$runtime_root" "$runtime_root/releases" "$release" "$release/wheel" "$runtime_root/state" "$runtime_root/workspace" "$runtime_root/recovery"
"$python_bin" -m pip wheel --no-deps --no-build-isolation --wheel-dir "$release/wheel" "$source_root"
set -- "$release/wheel"/*.whl; [ "$#" -eq 1 ] || exit 2
"$python_bin" -m venv "$release/venv"; "$release/venv/bin/pip" install --no-deps "$1"
token="$runtime_root/token"; if [ ! -e "$token" ]; then "$python_bin" -c 'import pathlib,secrets,sys; pathlib.Path(sys.argv[1]).write_text(secrets.token_urlsafe(48)+"\n")' "$token"; fi; chmod 600 "$token"
bind_host=$("$release/venv/bin/wechat-codex-bridge-admin" discover | "$python_bin" -c 'import json,sys; print(json.load(sys.stdin)["bind"])')
service="$HOME/.config/systemd/user/wechat-codex-bridge.service"; template="$source_root/deploy/linux/wechat-codex-bridge.service.template"
sed -e "s|__PROGRAM__|$release/venv/bin/wechat-codex-bridge|g" -e "s|__BIND_HOST__|$bind_host|g" -e "s|__TOKEN__|$token|g" -e "s|__STATE__|$runtime_root/state|g" -e "s|__WORKSPACE__|$runtime_root/workspace|g" -e "s|__CODEX__|$codex_bin|g" -e "s|__HOME__|$HOME|g" "$template" > "$service"
chmod 600 "$service"; ln -sfn "$release" "$runtime_root/current"
systemctl --user daemon-reload; systemctl --user enable --now wechat-codex-bridge.service
echo "service=wechat-codex-bridge bind=$bind_host:18791"
