#!/usr/bin/env bash
# 构建并发布站点到 GitHub Pages（gh-pages 分支）
#
# 用法：
#   ./scripts/deploy_pages.sh            # 构建 + 发布
#   ./scripts/deploy_pages.sh --no-build # 直接发布当前 outputs/medtrain
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REPO_URL="https://github.com/chefzs929-prog/yingzhi-medtrain.git"
TMP="$ROOT/.deepworks/tmp/site"

if [[ "${1:-}" != "--no-build" ]]; then
  echo "==> 生成知识库（kb/data -> outputs/medtrain/data）"
  python3 medtrain/build_data.py
  echo "==> 打包前端"
  python3 medtrain/build.py
fi

if [[ ! -f outputs/medtrain/index.html ]]; then
  echo "缺少 outputs/medtrain/index.html，先运行不带 --no-build 的完整构建" >&2
  exit 1
fi

echo "==> 准备发布目录（排除排查用 kb.json 与临时文件）"
rm -rf "$TMP"
mkdir -p "$TMP"
rsync -a \
  --exclude '_work/' \
  --exclude 'data/kb.json' \
  --exclude '.DS_Store' \
  outputs/medtrain/ "$TMP/"
touch "$TMP/.nojekyll"

cd "$TMP"
git init -q -b gh-pages
git add -A
git -c user.name="${GIT_AUTHOR_NAME:-chefzs929-prog}" \
    -c user.email="${GIT_AUTHOR_EMAIL:-chefzs929@gmail.com}" \
    commit -q -m "deploy: $(date '+%Y-%m-%d %H:%M')"
git remote add origin "$REPO_URL"
GIT_TERMINAL_PROMPT=0 git push -f origin gh-pages

echo "==> 已推送 gh-pages，等待 Pages 构建（约 1-2 分钟）"
echo "    https://chefzs929-prog.github.io/yingzhi-medtrain/"
