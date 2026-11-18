#!/usr/bin/env bash
# 启动影知本地服务。
#
#   yingzhi/serve/start.sh              # 用 .env 里的配置启动
#   yingzhi/serve/start.sh --offline    # 强制本地降级，不调任何模型
#   PORT=8801 yingzhi/serve/start.sh    # 换端口
#
# 没有配 key 也能启动，会自动退回本地规则引擎，界面上显示「未调用 Agent」。
set -euo pipefail

cd "$(dirname "$0")/../.."
ENV_FILE="yingzhi/serve/.env"

if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  echo "已读取 $ENV_FILE"
else
  echo "未找到 $ENV_FILE（可从 env.example 复制一份）"
fi

if [ -z "${YZ_LLM_TEXT_KEY:-}" ] && [ -z "${YZ_LLM_VISION_KEY:-}" ]; then
  echo "提示：未配置任何模型 key，本次以纯本地规则引擎运行。"
else
  echo "文本模型：${YZ_LLM_TEXT_MODEL:-未配置}"
  echo "视觉模型：${YZ_LLM_VISION_MODEL:-未配置（走文本兜底）}"
fi

exec python3 yingzhi/serve/main.py --port "${PORT:-8800}" "$@"
