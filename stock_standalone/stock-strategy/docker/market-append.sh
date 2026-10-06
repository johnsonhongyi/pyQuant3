#!/bin/sh
set -eu

PROJECT=/root/johnson/stock-strategy
DATA_ROOT=/mnt/4TB/dockerf/stockstrategy
SERVICE="$PROJECT/source/easy-stock-service"
LOG_ROOT="$DATA_ROOT/logs/service"
LOCK_ROOT="$DATA_ROOT/data/service/locks"

case "${1:-}" in
    cn)
        script=bars.py
        log_file="$LOG_ROOT/market-append-cn.log"
        lock_file="$LOCK_ROOT/market-append-cn.lock"
        ;;
    us)
        script=bars_us.py
        log_file="$LOG_ROOT/market-append-us.log"
        lock_file="$LOCK_ROOT/market-append-us.lock"
        ;;
    *)
        printf 'usage: %s {cn|us}\n' "$0" >&2
        exit 2
        ;;
esac

umask 022
mkdir -p "$LOG_ROOT" "$LOCK_ROOT"
(
    exec 9>"$lock_file"
    if ! /usr/bin/flock -n 9; then
        printf '[%s] %s append already running; skipped\n' "$(date -Is)" "$1"
        exit 0
    fi

    export EASY_STOCK_DATA_DB="$DATA_ROOT/data/easy-stock/stock-data.db"
    export TRADING_CALENDAR_PATH="$DATA_ROOT/config/trading-calendar.json"
    export PYTHONUNBUFFERED=1

    printf '[%s] %s append started\n' "$(date -Is)" "$1"
    cd "$SERVICE"
    if /usr/bin/python3 "$SERVICE/$script" --append; then
        printf '[%s] %s append finished\n' "$(date -Is)" "$1"
    else
        status=$?
        printf '[%s] %s append failed (exit=%s)\n' "$(date -Is)" "$1" "$status"
        exit "$status"
    fi
) >> "$log_file" 2>&1
