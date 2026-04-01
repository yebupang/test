#!/bin/bash
# 投资助手启动脚本（本地开发）

set -e

ROOT=$(cd "$(dirname "$0")" && pwd)
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

echo "=============================="
echo "  投资助手 — 本地启动"
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
  npm run dev &
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
echo "  按 Ctrl+C 停止所有服务"
echo "=============================="

# 等待并在退出时清理
trap 'echo ""; echo "正在停止..."; kill $BACKEND_PID 2>/dev/null; kill $FRONTEND_PID 2>/dev/null; exit 0' INT TERM
wait
