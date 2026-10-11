#!/usr/bin/env bash
set -Eeuo pipefail

INSTOCK_DATA_ROOT=/mnt/4TB/dockerf/stock

instock_fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}

instock_require_external_disk() {
    mountpoint -q /mnt/4TB || instock_fail '/mnt/4TB is not mounted.'
    mountpoint -q /mnt/mariadb-data || instock_fail '/mnt/mariadb-data is not mounted.'
    for path in "$INSTOCK_DATA_ROOT/log" "$INSTOCK_DATA_ROOT/instockcache" \
        "$INSTOCK_DATA_ROOT/instrategy" "$INSTOCK_DATA_ROOT/forwardp"; do
        [ -d "$path" ] || instock_fail "Required external data directory is missing: $path"
        resolved=$(realpath -e -- "$path") || instock_fail "Cannot resolve external path: $path"
        case "$resolved" in /mnt/4TB/*) ;; *) instock_fail "External path is outside /mnt/4TB: $resolved" ;; esac
    done
    [ -d /mnt/mariadb-data/mariadb/data ] || instock_fail 'MariaDB persistent data directory is missing.'
}

instock_require_bind() {
    local container source destination mounts
    container=$1
    source=$2
    destination=$3
    mounts=$(docker inspect --format '{{range .Mounts}}{{printf "%s\t%s\t%s\t%t\n" .Type .Source .Destination .RW}}{{end}}' "$container") \
        || instock_fail "Cannot inspect mounts for $container."
    printf '%s\n' "$mounts" | awk -F '\t' -v source="$source" -v destination="$destination" \
        '$1 == "bind" && $2 == source && $3 == destination && $4 == "true" {found=1} END {exit !found}' \
        || instock_fail "$container is missing the existing bind mount $source -> $destination (rw=true)."
}

instock_assert_existing_data_mounts() {
    local container count
    container=$1
    count=$(docker inspect --format '{{len .Mounts}}' "$container") || instock_fail "Cannot inspect mounts for $container."
    [ "$count" = 4 ] || instock_fail "$container has $count mounts; the verified existing contract has exactly 4."
    instock_require_bind "$container" "$INSTOCK_DATA_ROOT/instockcache" /data/InStock/instock/cache
    instock_require_bind "$container" "$INSTOCK_DATA_ROOT/instrategy" /data/InStock/instock/core/strategy
    instock_require_bind "$container" "$INSTOCK_DATA_ROOT/forwardp" /data/InStock/instock/forwardp
    instock_require_bind "$container" "$INSTOCK_DATA_ROOT/log" /data/InStock/instock/log
}

instock_assert_managed_mounts() {
    instock_assert_existing_data_mounts "$1"
}

instock_assert_mariadb_mounts() {
    local count
    count=$(docker inspect --format '{{len .Mounts}}' mariadb) || instock_fail 'Cannot inspect MariaDB mounts.'
    [ "$count" = 1 ] || instock_fail "MariaDB has $count mounts; the verified existing contract has exactly 1."
    instock_require_bind mariadb /mnt/mariadb-data/mariadb/data /var/lib/mysql
}
