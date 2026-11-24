#!/bin/bash
# 构建 macOS 桌面入口：Objective-C + WKWebView + 内置 Python 静态服务。
# 产物：
#   outputs/desktop/RadioCheck.app
#   outputs/desktop/RadioCheck.dmg
#   outputs/desktop/RadioCheck-macOS.zip
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$ROOT/desktop/RadioCheck"
SITE="$ROOT/outputs/medtrain"
OUT="$ROOT/outputs/desktop"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/radiocheck.XXXXXX")"
APP="$WORK/RadioCheck.app"
ICONSET="$WORK/AppIcon.iconset"
ARCH="$(uname -m)"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$OUT"

if [ ! -f "$SITE/read/clinic.html" ]; then
  echo "==> 站点未构建，先运行 medtrain/build.py"
  python3 "$ROOT/medtrain/build.py"
fi

echo "==> 清理旧产物"
rm -rf "$APP" "$ICONSET"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

echo "==> 编译原生壳（$ARCH）"
SDK="$(xcrun --show-sdk-path)"
clang -fobjc-arc -O -isysroot "$SDK" -mmacosx-version-min=11.0 \
  -framework Cocoa -framework WebKit \
  "$SRC/main.m" "$SRC/RCServer.m" \
  -o "$APP/Contents/MacOS/RadioCheck"

echo "==> 组装 .app"
cp "$SRC/Info.plist" "$APP/Contents/Info.plist"
printf 'APPL????' > "$APP/Contents/PkgInfo"
# _work/ 是历史调试页，不随桌面版分发。
rsync -a --exclude '_work/' "$SITE/" "$APP/Contents/Resources/site/"

echo "==> 生成图标"
mkdir -p "$ICONSET"
make_icon() {
  sips -z "$1" "$1" "$SITE/icons/icon-512.png" --out "$ICONSET/$2" >/dev/null
}
make_icon 16   icon_16x16.png
make_icon 32   icon_16x16@2x.png
make_icon 32   icon_32x32.png
make_icon 64   icon_32x32@2x.png
make_icon 128  icon_128x128.png
make_icon 256  icon_128x128@2x.png
make_icon 256  icon_256x256.png
make_icon 512  icon_256x256@2x.png
make_icon 512  icon_512x512.png
make_icon 1024 icon_512x512@2x.png
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/AppIcon.icns"
rm -rf "$ICONSET"

echo "==> Ad-hoc 签名"
# Desktop 由 fileprovider 管理，会注入 FinderInfo/fileprovider xattr；
# 先清掉这两个，再 ad-hoc 签名，否则 codesign 会报 detritus。
xattr -cr "$APP" 2>/dev/null || true
xattr -d com.apple.FinderInfo "$APP" 2>/dev/null || true
xattr -d 'com.apple.fileprovider.fpfs#P' "$APP" 2>/dev/null || true
codesign --force --sign - "$APP" >/dev/null

echo "==> 生成 DMG / ZIP"
rm -f "$OUT/RadioCheck.dmg" "$OUT/RadioCheck-macOS.zip"
hdiutil create -volname "RadioCheck" -srcfolder "$APP" -ov -format UDZO \
  "$OUT/RadioCheck.dmg" >/dev/null
ditto -c -k --sequesterRsrc --keepParent "$APP" "$OUT/RadioCheck-macOS.zip"

echo "==> 复制 .app 到 outputs（本地直接双击用）"
rm -rf "$OUT/RadioCheck.app"
ditto --norsrc --noextattr "$APP" "$OUT/RadioCheck.app"

echo ""
echo "完成："
du -sh "$OUT/RadioCheck.app" "$OUT/RadioCheck.dmg" "$OUT/RadioCheck-macOS.zip"
echo "双击 $OUT/RadioCheck.app 启动；首次打开若被 Gatekeeper 拦截，右键 -> 打开。"
