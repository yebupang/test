#!/bin/bash
# watch.sh — 自动监听 git 更新并重启服务
#
# 用法:
#   ./watch.sh            前台运行（Ctrl+C 停止）
#   nohup ./watch.sh &    后台运行（关闭终端也持续运行）
#   tail -f watch.log     查看实时日志

set -uo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
BRANCH="claude/investment-assistant-planning-wuyQ5"
BACKEND="$REPO/backend"
FRONTEND="$REPO/frontend"
CHECK_INTERVAL=30
LOG="$REPO/watch.log"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

# ── 停止现有服务 ──────────────────────────────────────────
stop_services() {
  log "停止现有服务..."
  pkill -f "uvicorn main:app" 2>/dev/null || true
  pkill -f "next-server"      2>/dev/null || true
  pkill -f "next start"       2>/dev/null || true
  sleep 2
}

# ── 初始化环境 ────────────────────────────────────────────
setup_env() {
  # Python venv
  if [ ! -d "$BACKEND/.venv" ]; then
    log "创建 Python 虚拟环境..."
    python3 -m venv "$BACKEND/.venv"
  fi
  log "安装/更新后端依赖..."
  "$BACKEND/.venv/bin/pip" install -q -r "$BACKEND/requirements.txt"

  # Node 依赖
  if [ ! -d "$FRONTEND/node_modules" ]; then
    log "安装前端依赖..."
    cd "$FRONTEND" && npm install --legacy-peer-deps --silent
  fi
}

# ── 构建前端 ──────────────────────────────────────────────
build_frontend() {
  log "构建前端（请稍候 1~2 分钟）..."
  cd "$FRONTEND"
  if npm run build 2>&1 | tee -a "$LOG"; then
    log "构建成功 ✓"
    return 0
  else
    log "构建失败 ✗，查看日志: $LOG"
    return 1
  fi
}

# ── 启动服务 ──────────────────────────────────────────────
start_services() {
  # 后端
  cd "$BACKEND"
  "$BACKEND/.venv/bin/uvicorn" main:app --host 0.0.0.0 --port 8000 --reload >> "$LOG" 2>&1 &
  log "后端已启动 (PID=$!)"

  # 前端
  cd "$FRONTEND"
  npm start >> "$LOG" 2>&1 &
  log "前端已启动 (PID=$!)"

  TAIL_IP=$(tailscale ip -4 2>/dev/null || echo "")
  log "─────────────────────────────────"
  log "本机访问: http://localhost:3000"
  [ -n "$TAIL_IP" ] && log "远程访问: http://$TAIL_IP:3000"
  log "─────────────────────────────────"
}

# ── 完整更新流程 ──────────────────────────────────────────
# 先构建，构建成功后再切换（避免构建失败导致服务停摆）
deploy() {
  setup_env
  build_frontend || return 1
  stop_services
  start_services
}

trap 'log "收到停止信号，退出中..."; stop_services; exit 0' INT TERM

# ═══════════════════════════════════════════════════
log "══════════════════════════════════════════"
log "  投资助手自动更新服务"
log "  分支: $BRANCH"
log "  检查间隔: ${CHECK_INTERVAL}s"
log "  日志: $LOG"
log "══════════════════════════════════════════"

# 首次拉取并启动
cd "$REPO"
git pull -q
deploy || { log "首次启动失败，请检查日志"; exit 1; }

log "开始监听更新（每 ${CHECK_INTERVAL} 秒检查一次）..."

# ═══════════════════════════════════════════════════
# 轮询主循环
while true; do
  sleep "$CHECK_INTERVAL"

  cd "$REPO"
  git fetch origin "$BRANCH" -q 2>/dev/null || continue

  LOCAL=$(git rev-parse HEAD 2>/dev/null || echo "")
  REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null || echo "")

  [ "$LOCAL" = "$REMOTE" ] && continue  # 无更新，安静跳过

  SHORT_OLD=$(echo "$LOCAL"  | cut -c1-7)
  SHORT_NEW=$(echo "$REMOTE" | cut -c1-7)
  log "▶ 检测到新版本 $SHORT_OLD → $SHORT_NEW，开始更新..."

  git pull -q
  if deploy; then
    log "✓ 更新完成，服务已重启"
  else
    log "⚠ 更新失败（构建错误），旧版本保持运行中"
    # 构建失败时 stop_services 未被调用，旧进程仍在运行
  fi
done
