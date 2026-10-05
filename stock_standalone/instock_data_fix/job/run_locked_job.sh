#!/bin/sh

LOCK=/data/InStock/instock/cache/strategy_enter.lock
RUNTIME_LOG=/data/InStock/instock/log/cron_runtime.log
MODE=$1
LABEL=$2
shift 2

started=$(date +%s)
printf '%s start job=%s pid=%s mode=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$LABEL" "$$" "$MODE" >> "$RUNTIME_LOG"

case "$MODE" in
    nonblock)
        /usr/bin/flock -n -E 75 "$LOCK" "$@"
        result=$?
        ;;
    wait:*)
        wait_seconds=${MODE#wait:}
        case "$wait_seconds" in
            ''|*[!0-9]*)
                printf '%s invalid wait timeout for job=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$LABEL" >> "$RUNTIME_LOG"
                exit 64
                ;;
        esac
        /usr/bin/flock -w "$wait_seconds" -E 75 "$LOCK" "$@"
        result=$?
        ;;
    *)
        printf '%s invalid lock mode for job=%s mode=%s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$LABEL" "$MODE" >> "$RUNTIME_LOG"
        exit 64
        ;;
esac

elapsed=$(($(date +%s) - started))
if [ "$result" -eq 75 ]; then
    state=skipped_lock
elif [ "$result" -eq 0 ]; then
    state=completed
else
    state=failed
fi
printf '%s finish job=%s state=%s rc=%s elapsed_seconds=%s\n' \
    "$(date '+%Y-%m-%d %H:%M:%S')" "$LABEL" "$state" "$result" "$elapsed" >> "$RUNTIME_LOG"
exit "$result"
