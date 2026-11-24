#!/usr/bin/env bash
# 演示用隧道：把本机 Agent 服务临时暴露成 HTTPS 地址，Agent 始终只跑在这台 Mac 上。
#
# 用法：
#   ./scripts/demo_tunnel.sh              # 起服务 + 隧道，并打开浏览器
#   ./scripts/demo_tunnel.sh --no-open    # 只起服务与隧道，不自动开浏览器
#   PORT=8812 ./scripts/demo_tunnel.sh    # 换端口
#
# 说明：
#   - 隧道地址由 Cloudflare 随机分配，每次启动都会变；演示前跑一次，把地址发给评审即可。
#   - 服务同时托管站点与 /api，前端与 Agent 同源，页面里不需要再填地址。
#   - 关闭：在终端按 Ctrl-C，服务和隧道会一起退出。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PORT="${PORT:-8811}"
SITE="${SITE:-outputs/medtrain}"
CF="$ROOT/.deepworks/bin/cloudflared"
LOG_DIR="$ROOT/.deepworks/tmp"
SERVE_LOG="$LOG_DIR/demo_serve.log"
CF_LOG="$LOG_DIR/demo_tunnel.log"
URL_FILE="$LOG_DIR/demo_tunnel_url.txt"
OPEN_BROWSER=1

for arg in "$@"; do
  case "$arg" in
    --no-open) OPEN_BROWSER=0 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "未知参数：$arg" >&2; exit 2 ;;
  esac
done

mkdir -p "$LOG_DIR"

# ---------- 依赖 ----------
if ! command -v python3 >/dev/null 2>&1; then
  echo "缺少 python3" >&2; exit 1
fi

if [[ ! -x "$CF" ]]; then
  echo "==> 首次运行，下载 cloudflared"
  ARCH="$(uname -m)"
  case "$ARCH" in
    arm64|aarch64) CF_PKG="cloudflared-darwin-arm64.tgz" ;;
    x86_64)        CF_PKG="cloudflared-darwin-amd64.tgz" ;;
    *) echo "不支持的架构：$ARCH" >&2; exit 1 ;;
  esac
  mkdir -p "$(dirname "$CF")"
  curl -fsSL --max-time 180 -o "$LOG_DIR/cloudflared.tgz" \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/$CF_PKG"
  tar -xzf "$LOG_DIR/cloudflared.tgz" -C "$(dirname "$CF")"
  chmod +x "$CF"
fi

# ---------- 端口 ----------
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "端口 $PORT 已被占用，换个端口：PORT=8812 $0" >&2
  exit 1
fi

SERVE_PID=""
CF_PID=""
CAFFEINATE_PID=""

cleanup() {
  echo
  echo "==> 正在停止"
  [[ -n "$CF_PID" ]] && kill "$CF_PID" 2>/dev/null || true
  [[ -n "$CAFFEINATE_PID" ]] && kill "$CAFFEINATE_PID" 2>/dev/null || true
  [[ -n "$SERVE_PID" ]] && kill "$SERVE_PID" 2>/dev/null || true
  rm -f "$URL_FILE"
  wait 2>/dev/null || true
  echo "==> 已停止"
}
trap cleanup EXIT INT TERM

# ---------- 本地服务（站点 + /api 同源） ----------
echo "==> 启动本地服务 :$PORT"
python3 yingzhi/serve/main.py --port "$PORT" --site "$SITE" > "$SERVE_LOG" 2>&1 &
SERVE_PID=$!

HEALTH=""
for _ in $(seq 1 40); do
  HEALTH="$(curl -s -m 2 "http://127.0.0.1:$PORT/api/health" || true)"
  [[ -n "$HEALTH" ]] && break
  sleep 0.5
done

if [[ -z "$HEALTH" ]]; then
  echo "本地服务没有起来，日志：$SERVE_LOG" >&2
  tail -20 "$SERVE_LOG" >&2 || true
  exit 1
fi

python3 - "$HEALTH" <<'PY'
import json, sys
try:
    d = json.loads(sys.argv[1])
except Exception:
    print("  health 返回无法解析"); raise SystemExit(0)
print("  服务就绪  ok=%s  agent=%s  skill=%s" % (d.get("ok"), d.get("agent_ready"), d.get("skill_ready")))
if not d.get("agent_ready"):
    print("  警告：Agent 未就绪（DeepWorks 是否在运行？），问答会降级。")
PY

if ! curl -s -o /dev/null -m 3 "http://127.0.0.1:$PORT/read/clinic.html"; then
  echo "站点未托管，检查 --site 路径：$SITE" >&2
fi

# ---------- 隧道 ----------
echo "==> 建立隧道（Cloudflare 随机域名）"
"$CF" tunnel --url "http://127.0.0.1:$PORT" --no-autoupdate > "$CF_LOG" 2>&1 &
CF_PID=$!

# 防止演示期间休眠断线
if command -v caffeinate >/dev/null 2>&1; then
  caffeinate -dimsu -w "$CF_PID" >/dev/null 2>&1 &
  CAFFEINATE_PID=$!
fi

URL=""
for _ in $(seq 1 90); do
  URL="$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$CF_LOG" | head -1 || true)"
  [[ -n "$URL" ]] && break
  sleep 0.5
done

if [[ -z "$URL" ]]; then
  echo "隧道地址解析失败，日志：$CF_LOG" >&2
  tail -20 "$CF_LOG" >&2 || true
  exit 1
fi

echo "==> 地址已分配：$URL"
echo "==> 等待公网生效（首次通常 20–90 秒）"
OK=0
for i in $(seq 1 90); do
  CODE="$(curl -s -o /dev/null -w '%{http_code}' -m 8 "$URL/api/health" || true)"
  if [[ "$CODE" == "200" ]]; then OK=1; break; fi
  if (( i % 15 == 0 )); then echo "    仍在等待…（$((i * 2))s）"; fi
  sleep 2
done

if [[ "$OK" != "1" ]]; then
  echo "公网暂不可达（$CODE）。域名可能仍在注册，稍等 1–2 分钟再刷新：$URL" >&2
fi

printf '%s\n' "$URL" > "$URL_FILE"

CLINIC="$URL/read/clinic.html"
COMPARE="$URL/read/compare.html"

cat <<EOF

────────────────────────────────────────────────
 演示地址（完整站点，直接发给评审）
   $URL/

 阅片工作台（Agent 问答）
   $CLINIC

 对比阅片
   $COMPARE
────────────────────────────────────────────────
 提示
   · 首次回答约 15–25 秒，页面会先显示检索过程，属正常。
   · Agent 只在这台 Mac 上运行；关闭终端或合盖即断开。
   · 不要用 GitHub Pages 地址演示，那边是纯静态版，没有 Agent。
   · 按 Ctrl-C 停止服务与隧道。
────────────────────────────────────────────────
EOF

if command -v pbcopy >/dev/null 2>&1; then
  printf '%s' "$URL/" | pbcopy || true
  echo " 演示地址已复制到剪贴板"
fi

if [[ "$OPEN_BROWSER" == "1" ]] && command -v open >/dev/null 2>&1; then
  open "$URL/"
fi

wait "$CF_PID"
