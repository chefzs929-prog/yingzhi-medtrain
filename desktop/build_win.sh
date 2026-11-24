#!/usr/bin/env bash
# 打包 Windows 免安装版：自带 Python 便携运行时，解压双击即用。
#
#   ./desktop/build_win.sh
#
# 产物：outputs/影知-Windows.zip
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST="$ROOT/desktop/win-dist"
CACHE="$ROOT/desktop/.cache"
PYVER="3.11.9"
PYZIP="$CACHE/python-$PYVER-embed-amd64.zip"
URL="https://www.python.org/ftp/python/$PYVER/python-$PYVER-embed-amd64.zip"

if [ ! -f "$ROOT/outputs/medtrain/index.html" ]; then
  echo "先构建站点：python3 medtrain/build.py" >&2
  exit 1
fi

mkdir -p "$CACHE"
if [ ! -f "$PYZIP" ]; then
  echo "下载 Python $PYVER embeddable …"
  curl -sSL --max-time 300 -o "$PYZIP" "$URL"
fi

rm -rf "$DIST"
mkdir -p "$DIST/python" "$DIST/site"

echo "解压运行时 …"
unzip -qo "$PYZIP" -d "$DIST/python"

echo "复制站点 …"
cp -R "$ROOT/outputs/medtrain/." "$DIST/site/"

echo "复制启动脚本 …"
cp "$ROOT/desktop/template-win/START.bat" "$DIST/START.bat"
cp "$ROOT/desktop/template-win/启动影知.bat" "$DIST/启动影知.bat"
cp "$ROOT/desktop/template-win/使用说明.txt" "$DIST/使用说明.txt"

mkdir -p "$ROOT/outputs"
ZIP="$ROOT/outputs/影知-Windows.zip"
rm -f "$ZIP"

python3 - "$DIST" "$ZIP" <<'PY'
import sys, zipfile
from pathlib import Path
src, dst = Path(sys.argv[1]), Path(sys.argv[2])
n = 0
with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for p in sorted(src.rglob("*")):
        if p.is_file():
            z.write(p, str(p.relative_to(src)))
            n += 1
print(f"{n} 个文件")
PY

echo "已生成：$ZIP  $(( $(wc -c < "$ZIP") / 1024 / 1024 ))MB"
