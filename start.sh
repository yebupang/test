#!/bin/bash
# 投资助手启动脚本
# 用法:
#   ./start.sh          — 生产模式（支持 Tailscale 远程访问）
#   ./start.sh --dev    — 开发模式（热重载，仅本机访问）

set -e

ROOT=$(cd "$(dirname "$0")" && pwd)
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

# 默认生产模式，--dev 参数切换到开发模式
MODE="prod"
if [ "$1" = "--dev" ]; then
  MODE="dev"
fi

echo "=============================="
if [ "$MODE" = "dev" ]; then
  echo "  投资助手 — 开发模式（热重载）"
else
  echo "  投资助手 — 生产模式（远程可访问）"
fi
echo "=============================="

# ── 检查 Python ──────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "[错误] 需要 Python 3.11+"
  exit 1
fi

# ── 后端环境 ─────────────────────────────────────────────
echo ""
echo "[1/4] 初始化后端 Python 环境..."
cd "$BACKEND"

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
  echo "  虚拟环境已创建"
fi

source .venv/bin/activate
pip install -q -r requirements.txt

# 复制 .env（首次）
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "  已生成 .env，请按需修改配置"
fi

# ── Node / 前端 ───────────────────────────────────────────
echo ""
echo "[2/4] 检查前端依赖..."
cd "$FRONTEND"

if ! command -v node &>/dev/null; then
  echo "[警告] 未找到 Node.js，跳过前端启动（仅后端 API 可用）"
  SKIP_FRONTEND=1
else
  if [ ! -d "node_modules" ]; then
    echo "  安装 npm 依赖..."
    npm install --legacy-peer-deps
  fi

  # 生产模式：以 .next/BUILD_ID 判断（dev 模式不生成此文件，避免误判）
  if [ "$MODE" = "prod" ]; then
    NEEDS_BUILD=0
    if [ ! -f ".next/BUILD_ID" ]; then
      NEEDS_BUILD=1
    elif find src -newer ".next/BUILD_ID" \( -name "*.ts" -o -name "*.tsx" -o -name "*.css" \) 2>/dev/null | grep -q .; then
      NEEDS_BUILD=1
    fi

    if [ "$NEEDS_BUILD" = "1" ]; then
      echo ""
      echo "[2.5/4] 构建前端..."
      npm run build
    else
      echo "  前端已是最新构建，跳过 build"
    fi
  fi
fi

# ── 启动服务 ──────────────────────────────────────────────
echo ""
echo "[3/4] 启动后端 (port 8000)..."
cd "$BACKEND"
source .venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
echo "  后端 PID: $BACKEND_PID"

sleep 2

if [ -z "$SKIP_FRONTEND" ]; then
  echo ""
  echo "[4/4] 启动前端 (port 3000)..."
  cd "$FRONTEND"
  if [ "$MODE" = "dev" ]; then
    npm run dev &
  else
    npm start &
  fi
  FRONTEND_PID=$!
  echo "  前端 PID: $FRONTEND_PID"
fi

echo ""
echo "=============================="
echo "  启动完成!"
echo "  后端 API: http://localhost:8000"
echo "  API 文档: http://localhost:8000/docs"
if [ -z "$SKIP_FRONTEND" ]; then
  echo "  前端界面: http://localhost:3000"
fi
TAIL_IP=$(tailscale ip -4 2>/dev/null)
if [ -n "$TAIL_IP" ]; then
  echo ""
  echo "  [Tailscale 远程访问]"
  echo "  前端界面: http://$TAIL_IP:3000"
  echo "  后端 API: http://$TAIL_IP:8000"
fi
echo "  按 Ctrl+C 停止所有服务"
echo "=============================="

# 等待并在退出时清理
trap 'echo ""; echo "正在停止..."; kill $BACKEND_PID 2>/dev/null; kill $FRONTEND_PID 2>/dev/null; exit 0' INT TERM
wait
