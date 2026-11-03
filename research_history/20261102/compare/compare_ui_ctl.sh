#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="${MC_COMPARE_PID_FILE:-$SCRIPT_DIR/.compare_ui.pid}"
PORT="${MC_COMPARE_PORT:-8765}"
HOST="${MC_COMPARE_HOST:-0.0.0.0}"
TMUX_SESSION="${MC_COMPARE_TMUX_SESSION:-mc_compare_ui}"

tmux_running() {
  command -v tmux >/dev/null 2>&1 && tmux has-session -t "$TMUX_SESSION" 2>/dev/null
}

running_pid() {
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(<"$PID_FILE")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      printf '%s' "$pid"
      return 0
    fi
    rm -f "$PID_FILE"
  fi
  local discovered
  discovered="$(pgrep -u "$UID" -f "^python3 ${SCRIPT_DIR}/compare_ui/server.py( |$)" | head -n 1 || true)"
  if [[ "$discovered" =~ ^[0-9]+$ ]] && kill -0 "$discovered" 2>/dev/null; then
    printf '%s\n' "$discovered" > "$PID_FILE"
    printf '%s' "$discovered"
    return 0
  fi
  return 1
}

start_ui() {
  local pid
  if pid="$(running_pid)"; then
    echo "MC Compare UI 已运行：PID $pid，http://127.0.0.1:$PORT"
    return
  fi
  if command -v tmux >/dev/null 2>&1; then
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
    local command
    printf -v command 'exec env MC_COMPARE_PID_FILE=%q MC_COMPARE_PORT=%q MC_COMPARE_HOST=%q %q' \
      "$PID_FILE" "$PORT" "$HOST" "$SCRIPT_DIR/run_compare_ui.sh"
    tmux new-session -d -s "$TMUX_SESSION" -c "$SCRIPT_DIR" "$command"
  else
    MC_COMPARE_PID_FILE="$PID_FILE" nohup "$SCRIPT_DIR/run_compare_ui.sh" </dev/null >/dev/null 2>&1 &
  fi
  for _ in {1..30}; do
    if pid="$(running_pid)"; then
      echo "MC Compare UI 已启动：PID $pid，http://127.0.0.1:$PORT"
      return
    fi
    sleep 0.1
  done
  if tmux_running; then
    tmux kill-session -t "$TMUX_SESSION" 2>/dev/null || true
  fi
  if [[ -f "$PID_FILE" ]]; then
    rm -f "$PID_FILE"
  fi
  echo "MC Compare UI 启动失败；可前台运行 run_compare_ui.sh 检查错误" >&2
  return 1
}

stop_ui() {
  local pid
  pid="$(running_pid || true)"
  if [[ -z "$pid" ]] && ! tmux_running; then
    echo "MC Compare UI 未运行"
    return
  fi
  if tmux_running; then
    tmux kill-session -t "$TMUX_SESSION"
  elif [[ -n "$pid" ]]; then
    kill "$pid"
  fi
  for _ in {1..50}; do
    if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      echo "MC Compare UI 已停止"
      return
    fi
    sleep 0.1
  done
  [[ -n "$pid" ]] && kill -KILL "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "MC Compare UI 已强制停止"
}

case "${1:-status}" in
  start) start_ui ;;
  stop) stop_ui ;;
  restart) stop_ui; start_ui ;;
  status)
    if pid="$(running_pid)"; then
      echo "MC Compare UI 运行中：PID $pid，http://127.0.0.1:$PORT"
    else
      echo "MC Compare UI 未运行"
      exit 1
    fi
    ;;
  *)
    echo "用法：$0 {start|stop|restart|status}" >&2
    exit 2
    ;;
esac
