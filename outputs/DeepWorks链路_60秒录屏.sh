#!/usr/bin/env bash
# 60 秒 DeepWorks 链路录屏（一键执行）
#
#   bash outputs/DeepWorks链路_60秒录屏.sh
#
# 流程：录屏开始 → 自动打开一个终端窗口执行「DeepWorks链路_演示.command」
# → 60 秒后保存。画面里是真实链路输出，不是后期合成。
#
# 注意：录制的是整个屏幕。开始前请关闭无关窗口，避免录到私人内容。

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
OUT="${OUT:-outputs/DeepWorks链路_60秒录屏.mov}"
DEMO="$(pwd)/outputs/DeepWorks链路_演示.command"
chmod +x "$DEMO" 2>/dev/null || true

echo "=============================================================="
echo " 60 秒 DeepWorks 链路录屏"
echo " 3 秒后开始录制，并自动打开终端窗口执行演示"
echo " 请先关闭无关窗口（录制范围是整个屏幕）"
echo "=============================================================="
sleep 3

screencapture -x -v -V 60 "$OUT" &
REC=$!
sleep 1

open -a Terminal "$DEMO" 2>/dev/null || {
  echo "自动打开终端失败，请手动双击：outputs/DeepWorks链路_演示.command"
}

wait $REC 2>/dev/null
echo
echo "已保存：$OUT"
