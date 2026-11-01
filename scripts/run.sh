#!/usr/bin/env bash
# ============================================================
# 文件名: scripts/run.sh
# 功能: 管理 Napcat + AullBot
# 用法:
#   ./scripts/run.sh start        # 后台启动 Napcat + Bot（screen）
#   ./scripts/run.sh dev          # 前台运行 Bot（Napcat 后台启动，调试用）
#   ./scripts/run.sh stop         # 仅停止 Bot（Napcat 继续运行）
#   ./scripts/run.sh stop-all     # 停止 Napcat + Bot
#   ./scripts/run.sh restart-bot  # 重启 Bot（不重启 Napcat）
#   ./scripts/run.sh restart      # 全量重启（Napcat + Bot）
#   ./scripts/run.sh status       # 查看状态（进程 / 端口 / 运行时长）
#   ./scripts/run.sh logs [N]     # 跟踪日志（默认 50 行）
#   ./scripts/run.sh check        # 环境自检（.env / 依赖 / 端口 / 目录）
#   ./scripts/run.sh test         # 跑回归测试
# ============================================================

set -euo pipefail

# ---------- 配置区（全部可用环境变量覆盖，方便换机器） ----------
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$PROJECT_DIR/.env"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/bot_run.log"
NAPCAST_SESSION="${NAPCAST_SESSION:-napcat}"
BOT_SESSION="${BOT_SESSION:-aullbot}"
NAPCAST_HOST="${NAPCAST_HOST:-127.0.0.1}"
NAPCAST_PROCESS_KEY="${NAPCAST_PROCESS_KEY:-}"
NAPCAST_CMD="${NAPCAST_CMD:-}"
NAPCAST_DIR="${NAPCAST_DIR:-}"
BOT_PATTERN='aullbot\.main'
export PYTHONUNBUFFERED=1

# NapCat 安装目录：优先 $NAPCAST_DIR，其次常见位置
detect_napcat_dir() {
    local cand
    for cand in "${NAPCAST_DIR:-}" "$PROJECT_DIR/Napcat" "$HOME/Napcat" /root/Napcat /opt/Napcat; do
        [ -n "$cand" ] && [ -x "$cand/opt/QQ/qq" ] && { echo "$cand"; return 0; }
    done
    return 1
}

# NapCat 由谁管理：skip_setup=false 时 ncatbot 会自动安装/启动/登录，run.sh 不要插手
napcat_auto_managed() {
    grep -qE '^[[:space:]]*skip_setup:[[:space:]]*false' "$PROJECT_DIR/config.yaml" 2>/dev/null
}

# WebSocket 端口：优先环境变量，其次读 config.yaml，最后 3001
detect_port() {
    if [ -n "${NAPCAST_PORT:-}" ]; then echo "$NAPCAST_PORT"; return; fi
    local p
    p=$(grep -oE 'ws://[^:/]+:[0-9]+' "$PROJECT_DIR/config.yaml" 2>/dev/null | head -1 | grep -oE '[0-9]+$')
    echo "${p:-3001}"
}
NAPCAST_PORT="$(detect_port)"

# 启动器：优先项目虚拟环境，其次 uv，最后系统 python3
resolve_launcher() {
    if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
        PY_BIN="$PROJECT_DIR/.venv/bin/python"
        BOT_CMD=("$PY_BIN" -u -m aullbot.main)
    elif command -v uv >/dev/null 2>&1; then
        PY_BIN="$(command -v python3 || echo python3)"
        BOT_CMD=(uv run python -u -m aullbot.main)
    else
        PY_BIN="$(command -v python3 || echo python3)"
        BOT_CMD=("$PY_BIN" -u -m aullbot.main)
    fi
}

# QQ 启动命令：NapCat 是无头 QQ，始终需要 xvfb-run（它是 NapCat 的依赖）
build_napcat_cmd() {
    local qq="$1/opt/QQ/qq"
    NAPCAST_CMD="xvfb-run -a ${qq} --no-sandbox -q ${QQ_NUMBER}"
    NAPCAST_PROCESS_KEY="qq.*-q ${QQ_NUMBER}"
    if ! command -v xvfb-run >/dev/null 2>&1; then
        echo "⚠️  缺少 xvfb-run（NapCat 的依赖），NapCat 将无法启动"
        echo "    Debian/Ubuntu: apt install xvfb ；Termux: pkg install x11-repo xorg-xvfb"
    fi
}

mkdir -p "$LOG_DIR"
cd "$PROJECT_DIR" || { echo "❌ 项目目录不存在: $PROJECT_DIR"; exit 1; }

# ---------- 辅助函数 ----------
load_env() {
    if [ ! -f "$ENV_FILE" ]; then
        echo "❌ .env 文件不存在，请检查: $ENV_FILE"
        exit 1
    fi
    _load_env_body
}

# 可选加载：check / logs / status 在缺 .env 时也要能跑
load_env_optional() {
    if [ -f "$ENV_FILE" ]; then
        _load_env_body
    else
        echo "⚠️  未找到 .env（check 仍会继续）"
        resolve_launcher
        NAPCAT_PORT="$(detect_port)"
        NAPCAST_PROCESS_KEY="qq.*-q ${QQ_NUMBER:-}"
    fi
}

_load_env_body() {
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
    if [ -z "${QQ_NUMBER:-}" ]; then
        echo "❌ .env 里没有 QQ_NUMBER"
        exit 1
    fi
    local napcat_dir
    if napcat_dir="$(detect_napcat_dir)"; then
        NAPCAST_DIR="$napcat_dir"
        build_napcat_cmd "$NAPCAST_DIR"
    else
        NAPCAST_DIR=""
        NAPCAST_CMD=""
        NAPCAST_PROCESS_KEY="qq.*-q ${QQ_NUMBER}"
        echo "⚠️  未找到 NapCat（可设 NAPCAST_DIR 指定），start 只会启动 Bot"
    fi
    resolve_launcher
    export TZ="${TZ:-Asia/Shanghai}"
    echo "✅ 已加载环境变量: $ENV_FILE"
    echo "   启动器 : ${BOT_CMD[*]}"
    echo "   NapCat : ${NAPCAST_DIR:-未找到}"
    echo "   端口   : $NAPCAST_PORT"
}

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# WebSocket 端口是否真的通（进程活着 ≠ 服务可用）
port_open() {
    local host="${1:-$NAPCAST_HOST}" port="${2:-$NAPCAST_PORT}"
    timeout 2 bash -c "exec 3<>/dev/tcp/${host}/${port}" 2>/dev/null
}

is_napcat_running() {
    pgrep -f "$NAPCAST_PROCESS_KEY" >/dev/null 2>&1
}

napcat_pids() {
    pgrep -f "$NAPCAST_PROCESS_KEY" | tr '\n' ' ' | sed 's/ $//'
}

bot_pids() {
    pgrep -f "$BOT_PATTERN" | tr '\n' ' ' | sed 's/ $//'
}

is_screen_session() {
    # 忽略 Dead 会话：它们只是残留记录，screen -X quit 也清不掉
    if screen -ls 2>/dev/null | grep -E "\.$1[[:space:]]" | grep -qv "Dead"; then
        return 0
    fi
    # 兜底：proot/Termux 下 screen 会话可能不注册 socket，但进程仍在
    case "$1" in
        "$BOT_SESSION") pgrep -f "$BOT_PATTERN" >/dev/null 2>&1 ;;
        "$NAPCAST_SESSION") is_napcat_running ;;
        *) return 1 ;;
    esac
}

uptime_of() {
    local pid
    pid=$(pgrep -f "$1" | head -1)
    [ -n "$pid" ] && ps -o etime= -p "$pid" 2>/dev/null | tr -d ' ' || true
}

# ---------- 启动 Napcat ----------
start_napcat() {
    if napcat_auto_managed; then
        log "ℹ️  config.yaml 里 skip_setup=false，NapCat 由 ncatbot 自动安装/启动/登录，这里不重复拉起"
        return 0
    fi
    if [ -z "${NAPCAST_CMD:-}" ]; then
        log "⚠️ 未找到 NapCat，跳过（只用 NAPCAST_DIR 指定路径后才会启动）"
        return 0
    fi
    if is_napcat_running; then
        if port_open; then
            log "✅ Napcat 已在运行（PID: $(napcat_pids)），端口 ${NAPCAST_PORT} 正常"
            return 0
        fi
        # 进程活着但端口不通：常见于 QQ 掉线重登后 NapCat 没接管
        log "⚠️ Napcat 进程存在（PID: $(napcat_pids)）但端口 ${NAPCAST_PORT} 不通，判定为僵死，重启"
        pkill -f "$NAPCAST_PROCESS_KEY" || true
        screen -X -S "$NAPCAST_SESSION" quit 2>/dev/null || true
        sleep 2
    fi

    screen -wipe >/dev/null 2>&1 || true   # 清掉 Dead 会话记录

    if is_screen_session "$NAPCAST_SESSION"; then
        log "⚠️ 发现残留 screen 会话 $NAPCAST_SESSION，清理中..."
        screen -X -S "$NAPCAST_SESSION" quit 2>/dev/null || true
        sleep 1
    fi

    log "🚀 启动 Napcat ..."
    screen -dmS "$NAPCAST_SESSION" bash -c "$NAPCAST_CMD"

    # 等端口就绪（比等进程准确）
    local i=0
    while [ "$i" -lt 45 ]; do
        if port_open; then
            log "✅ Napcat 启动成功（PID: $(napcat_pids)，端口 ${NAPCAST_PORT}）"
            return 0
        fi
        sleep 1
        i=$((i + 1))
    done
    log "❌ Napcat 启动超时：端口 ${NAPCAST_PORT} 仍不通"
    if is_napcat_running; then
        log "   QQ 进程在（PID: $(napcat_pids)）但服务没起来，通常是掉线需要重新登录："
        log "   screen -r $NAPCAST_SESSION      # 进去看/扫码，Ctrl+A D 退出"
    else
        log "   QQ 进程都没起来，检查: tail -f ~/.screen/$NAPCAST_SESSION 或 screen -r $NAPCAST_SESSION"
    fi
    return 1
}

# ---------- 后台启动 Bot ----------
start_bot_daemon() {
    if is_screen_session "$BOT_SESSION"; then
        log "✅ Bot 已在运行（PID: $(bot_pids)）"
        return 0
    fi
    screen -wipe >/dev/null 2>&1 || true
    log "🚀 后台启动 AullBot (screen) ..."
    local cmd_str="cd '$PROJECT_DIR' && ${BOT_CMD[*]} 2>&1 | tee -a '$LOG_FILE'"
    screen -dmS "$BOT_SESSION" bash -c "$cmd_str"

    local i=0
    while [ "$i" -lt 30 ]; do
        if pgrep -f "$BOT_PATTERN" >/dev/null 2>&1; then
            log "✅ Bot 后台启动成功（PID: $(bot_pids)）"
            log "   查看日志: ./scripts/run.sh logs"
            return 0
        fi
        sleep 1
        i=$((i + 1))
    done
    log "❌ Bot 启动失败，最近日志："
    tail -n 20 "$LOG_FILE" || true
    return 1
}

# ---------- 前台运行 Bot ----------
run_bot_foreground() {
    log "🚀 前台启动 AullBot（Ctrl+C 退出）..."
    exec "${BOT_CMD[@]}"
}

# ---------- 停止 ----------
stop_service() {
    local session=$1
    if ! is_screen_session "$session"; then
        log "ℹ️  $session 未运行"
        return 0
    fi
    log "🛑 停止 $session ..."
    screen -X -S "$session" quit 2>/dev/null || true
    sleep 1
    if ! is_screen_session "$session"; then
        log "✅ $session 已停止"
        return 0
    fi
    log "⚠️ screen 无法正常停止，改用 kill"
    screen -X -S "$session" kill 2>/dev/null || true
    sleep 1
    if is_screen_session "$session"; then
        log "⚠️ 会话未注册，按进程强制终止 $session"
        case "$session" in
            "$BOT_SESSION") pkill -f "$BOT_PATTERN" || true ;;
            "$NAPCAST_SESSION") pkill -f "$NAPCAST_PROCESS_KEY" || true ;;
        esac
        sleep 1
    fi
}

stop_bot() {
    stop_service "$BOT_SESSION"
}

stop_all() {
    stop_service "$BOT_SESSION"
    if napcat_auto_managed; then
        log "ℹ️  skip_setup=false，NapCat 不由本脚本管理，只停 Bot"
        return 0
    fi
    stop_service "$NAPCAST_SESSION"
    if is_napcat_running; then
        log "⚠️ 仍有残留 Napcat 进程，强制终止..."
        pkill -f "$NAPCAST_PROCESS_KEY" || true
        sleep 2
    fi
    if port_open; then
        log "⚠️ 端口 ${NAPCAST_PORT} 仍被占用，可能还有其它进程"
    else
        log "✅ Napcat 已完全停止"
    fi
}

# ---------- 状态 ----------
status() {
    echo "----------- 运行状态 -----------"
    if napcat_auto_managed; then
        echo "ℹ️  模式:      ncatbot 托管 NapCat（skip_setup=false）"
    else
        echo "ℹ️  模式:      本脚本托管 NapCat（skip_setup=true）"
    fi
    if is_napcat_running; then
        if port_open; then
            echo "✅ Napcat:  运行中 (PID: $(napcat_pids), 端口 ${NAPCAST_PORT} 正常, 已运行 $(uptime_of "$NAPCAST_PROCESS_KEY"))"
        else
            echo "⚠️  Napcat:  进程在 (PID: $(napcat_pids)) 但端口 ${NAPCAST_PORT} 不通 ← 僵死，跑 stop-all 重来"
        fi
    else
        echo "❌ Napcat:  未运行"
    fi

    if pgrep -f "$BOT_PATTERN" >/dev/null 2>&1; then
        echo "✅ Bot:     运行中 (PID: $(bot_pids), 已运行 $(uptime_of "$BOT_PATTERN"))"
    else
        echo "❌ Bot:     未运行"
    fi

    if [ -f "$LOG_FILE" ]; then
        echo "📄 日志:    $LOG_FILE ($(du -h "$LOG_FILE" | cut -f1))"
        local last
        last=$(grep -a "导入耗时\|监控已启动\|Traceback" "$LOG_FILE" | tail -1 || true)
        [ -n "$last" ] && echo "   最近:    ${last:0:100}"
    fi
    echo "--------------------------------"
}

# ---------- 日志 ----------
show_logs() {
    local lines="${1:-50}"
    [ -f "$LOG_FILE" ] || { echo "日志不存在: $LOG_FILE"; exit 1; }
    echo "📄 tail -f $LOG_FILE（Ctrl+C 退出）"
    tail -n "$lines" -f "$LOG_FILE"
}

# ---------- 环境自检 ----------
check_env() {
    local fail=0
    echo "----------- 环境自检 -----------"

    if [ -f "$ENV_FILE" ]; then echo "✅ .env 存在"; else echo "❌ .env 缺失"; fail=1; fi

    local var
    for var in LLM_API_KEY QQ_NUMBER; do
        if [ -n "${!var:-}" ]; then
            echo "✅ $var 已设置"
        else
            echo "❌ $var 未设置"
            fail=1
        fi
    done

    local bili=0
    for var in BILI_SESSDATA BILI_JCT BILI_DEDEUSERID; do
        [ -n "${!var:-}" ] && bili=$((bili + 1))
    done
    echo "ℹ️  B站凭据: $bili/3 项（缺了只影响 bilibili_monitor）"

    if [ -x "$PY_BIN" ]; then
        echo "✅ Python: $("$PY_BIN" -V 2>&1)"
    else
        echo "❌ 找不到 $PY_BIN"
        fail=1
    fi

    if "$PY_BIN" -c "import ncatbot, aullbot" 2>/dev/null; then
        echo "✅ 依赖可导入 (ncatbot, aullbot)"
    else
        echo "❌ 依赖导入失败，试: uv sync"
        fail=1
    fi

    # 运行依赖（换机器时最容易缺的）
    local dep missing_deps=""
    for dep in bash screen pgrep pkill timeout tee; do
        if command -v "$dep" >/dev/null 2>&1; then
            echo "✅ 命令可用: $dep"
        else
            echo "❌ 缺少命令: $dep"
            missing_deps="$missing_deps $dep"
            fail=1
        fi
    done
    if command -v uv >/dev/null 2>&1; then
        echo "✅ uv 可用（无 .venv 时用它启动）"
    else
        echo "ℹ️  没有 uv（有 .venv/bin/python 也能跑）"
    fi

    if napcat_auto_managed; then
        echo "ℹ️  skip_setup=false：NapCat 交给 ncatbot 自动安装/启动（本脚本不启动它）"
    elif [ -n "${NAPCAST_DIR:-}" ]; then
        echo "✅ NapCat 目录: $NAPCAST_DIR"
        # xvfb-run 是 NapCat（无头 QQ）的依赖，不是可选项
        if command -v xvfb-run >/dev/null 2>&1; then
            echo "✅ xvfb-run 可用（NapCat 依赖）"
        else
            echo "❌ 缺少 xvfb-run（NapCat 依赖）: apt install xvfb"
            fail=1
        fi
    else
        echo "❌ 未找到 NapCat（设 NAPCAST_DIR 指定，如 NAPCAST_DIR=/opt/Napcat）"
        fail=1
    fi

    if port_open; then
        echo "✅ Napcat 端口 ${NAPCAST_PORT} 可达"
    else
        echo "❌ Napcat 端口 ${NAPCAST_PORT} 不可达"
        fail=1
    fi

    local dir
    for dir in bot_data logs; do
        [ -d "$PROJECT_DIR/$dir" ] && echo "✅ 目录存在: $dir" || echo "⚠️  目录缺失: $dir"
    done

    if [ -f "$PROJECT_DIR/bot_data/template_config.json" ]; then
        echo "✅ 会话配置模板存在"
    else
        echo "⚠️  缺少 bot_data/template_config.json，新群将建不起来"
    fi

    echo "--------------------------------"
    if [ "$fail" -eq 0 ]; then
        echo "结论: 可以启动"
    else
        echo "结论: 有问题需要先处理（见上面的 ❌）"
    fi
    return "$fail"
}

# ---------- 回归测试 ----------
run_tests() {
    if [ ! -x "$PY_BIN" ]; then
        echo "❌ 找不到 $PY_BIN"
        exit 1
    fi
    exec "$PY_BIN" "$PROJECT_DIR/tests/test_bilibili_monitor.py"
}

usage() {
    cat <<'EOF'
用法: ./scripts/run.sh <命令>

  start        后台启动 Napcat + Bot (screen)
  dev          前台运行 Bot（Napcat 后台启动，调试用）
  stop         仅停止 Bot，Napcat 继续运行
  stop-all     停止 Napcat + Bot
  restart-bot  重启 Bot（不重启 Napcat）
  restart      全量重启（Napcat + Bot）
  status       查看状态（进程 / 端口 / 运行时长）
  logs [N]     跟踪日志（默认 50 行）
  check        环境自检（.env / 依赖 / 端口 / 目录）
  test         跑回归测试
EOF
}

# ---------- 主逻辑 ----------
case "${1:-start}" in
    status|logs|check)
        load_env_optional
        ;;
    *)
        load_env
        ;;
esac

case "${1:-start}" in
    start)
        start_napcat || exit 1
        start_bot_daemon || exit 1
        status
        ;;
    dev)
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
    restart)
        stop_all
        sleep 2
        start_napcat || exit 1
        start_bot_daemon || exit 1
        status
        ;;
    status)
        status
        ;;
    logs)
        show_logs "${2:-50}"
        ;;
    check)
        check_env
        ;;
    test)
        run_tests
        ;;
    *)
        usage
        exit 1
        ;;
esac
