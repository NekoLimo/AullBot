#!/usr/bin/bash
# ============================================================
# 文件名: start_bot.sh
# 功能: 管理 Napcat + AullBot，支持 start/stop/status/restart/dev
# 用法: 
#   ./start_bot.sh start        # 后台启动 Napcat + Bot（screen）
#   ./start_bot.sh dev          # 前台运行 Bot（Napcat 后台启动）
#   ./start_bot.sh stop         # 仅停止 Bot（Napcat 继续运行）
#   ./start_bot.sh stop-all     # 停止 Napcat + Bot
#   ./start_bot.sh restart-bot  # 重启 Bot（不重启 Napcat）
#   ./start_bot.sh status       # 查看状态
# ============================================================

set -euo pipefail

# ---------- 配置区 ----------
PROJECT_DIR="/root/AullBot"
ENV_FILE="$PROJECT_DIR/.env"
LOG_DIR="$PROJECT_DIR/logs"
NAPCAST_SESSION="napcat"
BOT_SESSION="aullbot"
# Napcat 启动命令（包含唯一 QQ 号）
NAPCAST_CMD="xvfb-run -a /root/Napcat/opt/QQ/qq --no-sandbox -q 3836808623"
# Bot 启动命令
UV_CMD="uv run python -m aullbot.main"
# 用于检测 Napcat 进程的关键字（确保唯一）
NAPCAST_PROCESS_KEY="qq.*-q 3836808623"

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR" || { echo "❌ 项目目录不存在: $PROJECT_DIR"; exit 1; }

# ---------- 辅助函数 ----------
load_env() {
    if [ -f "$ENV_FILE" ]; then
        set -a                # 自动导出所有变量
        source "$ENV_FILE"
        set +a
        echo "✅ 已加载环境变量: $ENV_FILE"
    else
        echo "⚠️ .env 文件不存在，请检查"
    fi
    export TZ='Asia/Shanghai'
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_DIR/bot_run.log"
}

# ---------- 进程检测 ----------
is_napcat_running() {
    pgrep -f "$NAPCAST_PROCESS_KEY" >/dev/null 2>&1
}

is_screen_session() {
    screen -ls | grep -q "\.$1\s" >/dev/null 2>&1
}

# ---------- 启动 Napcat（仅当未运行时） ----------
start_napcat() {
    if is_napcat_running; then
        log "✅ Napcat 进程已在运行（PID: $(pgrep -f "$NAPCAST_PROCESS_KEY" | tr '\n' ' ')），跳过启动"
        return 0
    fi

    # 清理残留 screen 会话
    if is_screen_session "$NAPCAST_SESSION"; then
        log "⚠️ 发现残留 screen 会话 $NAPCAST_SESSION，正在清理..."
        screen -X -S "$NAPCAST_SESSION" quit || true
    fi

    log "🚀 启动 Napcat ..."
    screen -dmS "$NAPCAST_SESSION" bash -c "$NAPCAST_CMD"
    # 等待进程出现（最多 30 秒）
    local count=0
    while ! is_napcat_running && [ $count -lt 30 ]; do
        sleep 1
        ((count++))
    done
    if is_napcat_running; then
        log "✅ Napcat 启动成功 (PID: $(pgrep -f "$NAPCAST_PROCESS_KEY" | tr '\n' ' '))"
        return 0
    else
        log "❌ Napcat 启动超时，请检查日志"
        return 1
    fi
}

# ---------- 后台启动 Bot（screen） ----------
start_bot_daemon() {
    if is_screen_session "$BOT_SESSION"; then
        log "✅ Bot 已在 screen 会话中运行"
        return 0
    fi
    load_env
    log "🚀 后台启动 AullBot (screen) ..."
    screen -dmS "$BOT_SESSION" bash -c "cd $PROJECT_DIR && $UV_CMD 2>&1 | tee -a $LOG_DIR/bot_run.log"
    sleep 2
    if is_screen_session "$BOT_SESSION"; then
        log "✅ Bot 后台启动成功"
        return 0
    else
        log "❌ Bot 后台启动失败，请检查日志"
        return 1
    fi
}

# ---------- 前台运行 Bot（直接在当前终端） ----------
run_bot_foreground() {   # 函数名保持不变，但被 dev 分支调用
    load_env
    log "🚀 前台启动 AullBot（日志将直接输出到终端）..."
    # 直接执行，脚本会阻塞，按 Ctrl+C 可终止 Bot
    exec $UV_CMD
}

# ---------- 停止服务 ----------
stop_service() {
    local session=$1
    if is_screen_session "$session"; then
        log "🛑 停止 $session ..."
        screen -X -S "$session" quit || true
        sleep 1
        if ! is_screen_session "$session"; then
            log "✅ $session 已停止"
        else
            log "⚠️ 无法正常停止，强制 kill"
            screen -X -S "$session" kill || true
        fi
    else
        log "ℹ️  $session 未运行"
    fi
}

# 停止 Bot（不停止 Napcat）
stop_bot() {
    stop_service "$BOT_SESSION"
}

# 停止全部（包括 Napcat 进程）
stop_all() {
    stop_service "$BOT_SESSION"
    stop_service "$NAPCAST_SESSION"
    # 如果 Napcat 进程残留（screen 已关但进程还在），精确 kill
    if is_napcat_running; then
        log "⚠️ 检测到残留 Napcat 进程，正在终止..."
        pkill -f "$NAPCAST_PROCESS_KEY" || true
        sleep 1
        if ! is_napcat_running; then
            log "✅ 残留 Napcat 已清理"
        fi
    fi
}

# ---------- 状态查看 ----------
status() {
    echo "----------- 运行状态 -----------"
    if is_napcat_running; then
        echo "✅ Napcat:  运行中 (PID: $(pgrep -f "$NAPCAST_PROCESS_KEY" | tr '\n' ' '))"
    else
        echo "❌ Napcat:  未运行"
    fi
    if is_screen_session "$BOT_SESSION"; then
        echo "✅ Bot:     运行中 (screen: $BOT_SESSION)"
    else
        echo "❌ Bot:     未运行"
    fi
    echo "------------------------------"
}

# ---------- 主命令调度 ----------
case "${1:-start}" in
    start)
        start_napcat || exit 1
        start_bot_daemon || exit 1
        status
        ;;
    dev)   # <-- 修改：将 run 改为 dev
        start_napcat || exit 1
        run_bot_foreground
        ;;
    stop)
        stop_bot
        ;;
    stop-all)
        stop_all
        ;;
    restart-bot)
        stop_bot
        sleep 2
        start_bot_daemon || exit 1
        status
        ;;
    status)
        status
        ;;
    *)
        echo "用法: $0 {start|dev|stop|stop-all|restart-bot|status}"   # <-- 修改
        echo "  start       后台启动 Napcat + Bot (screen)"
        echo "  dev         前台运行 Bot (Napcat 后台启动，调试用)"    # <-- 修改
        echo "  stop        仅停止 Bot，Napcat 继续运行"
        echo "  stop-all    停止 Napcat + Bot"
        echo "  restart-bot 重启 Bot（不重启 Napcat）"
        echo "  status      查看运行状态"
        exit 1
        ;;
esac