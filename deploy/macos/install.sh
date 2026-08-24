#!/bin/sh
set -eu
[ "$#" -eq 2 ] || { echo "usage: install.sh SOURCE_ROOT RUNTIME_ROOT" >&2; exit 2; }
source_root=$1; runtime_root=$2
case "$source_root:$runtime_root" in /*:/*) ;; *) echo "absolute paths required" >&2; exit 2;; esac
[ ! -L "$runtime_root" ] || { echo "runtime symlink rejected" >&2; exit 2; }
python_bin=${PYTHON_BIN:-python3}; codex_bin=${CODEX_BIN:-$(command -v codex || true)}
[ -x "$codex_bin" ] || { echo "codex unavailable" >&2; exit 2; }
stamp=$(date -u +%Y%m%dT%H%M%SZ); release="$runtime_root/releases/$stamp"
mkdir -p "$release/wheel" "$runtime_root/state" "$runtime_root/workspace" "$runtime_root/logs" "$runtime_root/recovery" "$HOME/Library/LaunchAgents"
chmod 700 "$runtime_root" "$runtime_root/releases" "$release" "$release/wheel" "$runtime_root/state" "$runtime_root/workspace" "$runtime_root/logs" "$runtime_root/recovery"
"$python_bin" -m pip wheel --no-deps --no-build-isolation --wheel-dir "$release/wheel" "$source_root"
set -- "$release/wheel"/*.whl; [ "$#" -eq 1 ] && [ -f "$1" ] || exit 2
"$python_bin" -m venv "$release/venv"; "$release/venv/bin/pip" install --no-deps "$1"
token="$runtime_root/token"
if [ ! -e "$token" ]; then "$python_bin" -c 'import pathlib,secrets,sys; pathlib.Path(sys.argv[1]).write_text(secrets.token_urlsafe(48)+"\n")' "$token"; fi
chmod 600 "$token"
rendered="$runtime_root/ai.wechat-codex-bridge.plist"
"$python_bin" - "$source_root/deploy/macos/ai.wechat-codex-bridge.plist.template" "$rendered" "$release/venv/bin/wechat-codex-bridge" "$token" "$runtime_root/state" "$runtime_root/workspace" "$codex_bin" "$HOME" "$runtime_root/logs/stdout.log" "$runtime_root/logs/stderr.log" <<'PY'
import html,sys
from pathlib import Path
src,out,*vals=sys.argv[1:]
keys=("__PROGRAM__","__TOKEN__","__STATE__","__WORKSPACE__","__CODEX__","__HOME__","__STDOUT__","__STDERR__")
text=Path(src).read_text()
for key,value in zip(keys,vals,strict=True): text=text.replace(key,html.escape(value,quote=True))
Path(out).write_text(text)
PY
chmod 600 "$rendered"; plutil -lint "$rendered" >/dev/null
plist="$HOME/Library/LaunchAgents/ai.wechat-codex-bridge.plist"; uid=$(id -u)
launchctl bootout "gui/$uid/ai.wechat-codex-bridge" 2>/dev/null || true
[ ! -e "$plist" ] || mv "$plist" "$runtime_root/recovery/ai.wechat-codex-bridge.plist.$stamp"
cp "$rendered" "$plist"; chmod 600 "$plist"; ln -sfn "$release" "$runtime_root/current"
launchctl bootstrap "gui/$uid" "$plist"
echo "service=ai.wechat-codex-bridge bind=127.0.0.1:18791"
