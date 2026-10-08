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
    crypto)
        script=bars_crypto.py
        log_file="$LOG_ROOT/market-append-crypto.log"
        lock_file="$LOCK_ROOT/market-append-crypto.lock"
        ;;
    *)
        printf 'usage: %s {cn|us|crypto}\n' "$0" >&2
        exit 2
        ;;
esac

umask 022
mkdir -p "$LOG_ROOT" "$LOCK_ROOT"
(
    exec 9>"$lock_file"
    if ! /usr/bin/flock -n 9; then
        printf '[%s] %s append already running; skipped\n' "$(date -Is)" "$1" >> "$log_file"
        exit 0
    fi

    rotate_log() {
        [ -f "$log_file" ] || return 0
        size=$(wc -c < "$log_file" | tr -d ' ')
        [ "$size" -ge 20971520 ] || return 0
        index=5
        while [ "$index" -gt 0 ]; do
            previous=$((index - 1))
            if [ "$previous" -eq 0 ]; then
                source=$log_file
            else
                source="$log_file.$previous"
            fi
            target="$log_file.$index"
            if [ -f "$source" ]; then
                if [ -f "$target" ]; then rm -f -- "$target"; fi
                mv -- "$source" "$target"
            fi
            index=$previous
        done
    }
    rotate_log
    exec >> "$log_file" 2>&1

    export EASY_STOCK_DATA_DB="$DATA_ROOT/data/easy-stock/stock-data.db"
    export TRADING_CALENDAR_PATH="$DATA_ROOT/config/trading-calendar.json"
    export PYTHONUNBUFFERED=1
    # The API has no host port; resolve its address on the managed bridge.
    api_address=$(docker inspect -f '{{with index .NetworkSettings.Networks "stockstrategy-net"}}{{.IPAddress}}{{end}}' stockstrategy-api 2>/dev/null || true)
    if [ -n "$api_address" ]; then
        export EASY_STOCK_API_URL="http://$api_address:20081"
    else
        printf '[%s] API container address unavailable; history backfill may fail\n' "$(date -Is)"
    fi

    printf '[%s] %s append started\n' "$(date -Is)" "$1"
    cd "$SERVICE"
    universe_status=0
    if [ "$1" = crypto ]; then
        if nice -n 10 /usr/bin/python3 "$SERVICE/crypto_universe.py" --refresh; then
            printf '[%s] crypto universe refresh finished\n' "$(date -Is)"
        else
            universe_status=$?
            printf '[%s] crypto universe refresh failed (exit=%s); continuing with the last known tracked universe\n' \
                "$(date -Is)" "$universe_status"
        fi
    fi
    if nice -n 10 /usr/bin/python3 "$SERVICE/$script" --append; then
        if [ "$universe_status" -ne 0 ]; then
            printf '[%s] crypto append completed with stale universe (refresh exit=%s)\n' \
                "$(date -Is)" "$universe_status"
            exit "$universe_status"
        fi
        printf '[%s] %s append finished\n' "$(date -Is)" "$1"
    else
        status=$?
        printf '[%s] %s append failed (exit=%s)\n' "$(date -Is)" "$1" "$status"
        exit "$status"
    fi
)
