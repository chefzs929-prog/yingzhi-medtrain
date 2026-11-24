#!/usr/bin/env bash
# 一键复现全部可执行验收。
#
# 用法：
#   bash scripts/verify_all.sh            # 全部
#   YZ_SKIP_BROWSER=1 bash scripts/verify_all.sh   # 只跑纯 Python 单测
#   YZ_PORT=8899 bash scripts/verify_all.sh        # 换端口
#
# 前置：
#   python3 -m pip install -r requirements.txt
#   python3 -m playwright install chromium     # 浏览器验收需要
#
# 退出码：0 = 全绿；1 = 有失败（会打印失败项所在阶段）。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${YZ_PORT:-8811}"
BASE="http://127.0.0.1:${PORT}/"
FAIL=0
SERVER_PID=""

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

section() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
run() {
  section "$*"
  "$@" || { echo "  ✗ 失败：$*"; FAIL=1; }
}

# ---------------------------------------------------------------- 1. 纯 Python 单测
section "Python 单测（无需浏览器）"
run python3 -m unittest kb.tests.test_kb kb.tests.test_region_api kb.tests.test_scope kb.tests.test_ask_citations
run python3 yingzhi/serve/test_semantic.py
run python3 yingzhi/serve/test_workflow.py
run python3 yingzhi/serve/test_chest_scope.py
run python3 kb/scripts/crosscheck.py

# ---------------------------------------------------------------- 2. 构建产物
section "构建产物"
if [ ! -d outputs/medtrain ]; then
  echo "outputs/medtrain 不存在，先构建"
  run python3 medtrain/build.py
else
  echo "  ✓ outputs/medtrain 已存在（跳过重建；需要最新产物请先 python3 medtrain/build.py）"
fi

# ---------------------------------------------------------------- 3. 浏览器验收
if [ "${YZ_SKIP_BROWSER:-0}" = "1" ]; then
  section "浏览器验收（已跳过：YZ_SKIP_BROWSER=1）"
else
  section "启动静态服务器 ${BASE}"
  (cd outputs/medtrain && python3 -m http.server "$PORT" >/dev/null 2>&1) &
  SERVER_PID=$!
  READY=0
  for _ in $(seq 1 40); do
    if curl -sf "$BASE" >/dev/null 2>&1; then READY=1; break; fi
    sleep 0.25
  done
  if [ "$READY" != "1" ]; then
    echo "  ✗ 静态服务器未就绪：$BASE"
    FAIL=1
  else
    echo "  ✓ 服务器就绪"
    export YZ_BASE="$BASE"
    run python3 medtrain/tests/refusal_eval.py
    run python3 medtrain/tests/ask_scope_check.py
    run python3 medtrain/tests/site_check.py
  fi
fi

# ---------------------------------------------------------------- 4. 汇总
section "汇总"
if [ "$FAIL" = "0" ]; then
  echo "全部通过。产物："
  echo "  outputs/medtrain/site_check.md"
  echo "  outputs/medtrain/refusal_eval.md"
  exit 0
else
  echo "存在失败项，见上面标 ✗ 的阶段。"
  exit 1
fi
