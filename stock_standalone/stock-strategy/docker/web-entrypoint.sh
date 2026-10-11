#!/bin/sh
set -eu

mkdir -p /logs/web
# Use this release's proxy configuration without changing the image or mounts.
if [ -f /usr/share/nginx/html/.runtime/nginx.conf ]; then
    sed 's@include /etc/nginx/conf.d/\*.conf;@include /usr/share/nginx/html/.runtime/nginx.conf;@' /etc/nginx/nginx.conf > /run/stockstrategy-nginx.conf
    nginx -t -c /run/stockstrategy-nginx.conf
    nginx -c /run/stockstrategy-nginx.conf -g 'daemon off;' &
else
    nginx -g 'daemon off;' &
fi
nginx_pid=$!

rotate_logs() {
    while sleep 60; do
        for log in /logs/web/access.log /logs/web/error.log; do
            [ -f "$log" ] || continue
            size=$(wc -c < "$log" | tr -d ' ')
            [ "$size" -ge 10485760 ] || continue
            mv "$log" "$log.$(date -u +%Y%m%dT%H%M%SZ)"
            nginx -s reopen
            count=0
            for rotated in $(ls -1t "$log".* 2>/dev/null || true); do
                count=$((count + 1))
                [ "$count" -le 3 ] || rm -f -- "$rotated"
            done
        done
    done
}

rotate_logs &
rotate_pid=$!
cleanup() {
    kill -TERM "$nginx_pid" "$rotate_pid" 2>/dev/null || true
    wait "$nginx_pid" 2>/dev/null || true
}
trap cleanup TERM INT
wait "$nginx_pid"
