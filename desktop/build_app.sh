#!/bin/bash
# 重新打包「影知.app」到桌面。改了站点之后运行本脚本即可。
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
SITE="$ROOT/outputs/medtrain"
TPL="$ROOT/desktop/template"
APP="$ROOT/desktop/build/影知.app"
DEST="$HOME/Desktop/影知.app"

[ -d "$SITE" ] || { echo "先运行 python3 medtrain/build.py"; exit 1; }

rm -rf "$APP" "$DEST"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp -R "$SITE" "$APP/Contents/Resources/site"
cp "$TPL/Info.plist" "$APP/Contents/Info.plist"
cp "$TPL/start" "$APP/Contents/MacOS/start"
chmod +x "$APP/Contents/MacOS/start"

# 图标
ICON_SRC="$SITE/icons/icon-512.png"
if [ -f "$ICON_SRC" ]; then
  TMP="$(mktemp -d)"
  mkdir -p "$TMP/app.iconset"
  for s in 16 32 64 128 256 512; do
    sips -z $s $s "$ICON_SRC" --out "$TMP/app.iconset/icon_${s}x${s}.png" >/dev/null 2>&1
    d=$((s * 2))
    sips -z $d $d "$ICON_SRC" --out "$TMP/app.iconset/icon_${s}x${s}@2x.png" >/dev/null 2>&1
  done
  iconutil -c icns "$TMP/app.iconset" -o "$APP/Contents/Resources/app.icns" 2>/dev/null || true
  rm -rf "$TMP"
fi

codesign --force --deep -s - "$APP" >/dev/null 2>&1 || true

cp -R "$APP" "$DEST"
echo "已更新：$DEST"
du -sh "$DEST"
