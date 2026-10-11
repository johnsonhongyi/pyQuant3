#!/usr/bin/env bash
set -Eeuo pipefail

if [ "$#" -ne 1 ]; then
    echo 'Usage: describe-instock-image.sh <image-tag-or-id>' >&2
    exit 2
fi

IMAGE=$1
if docker inspect "$IMAGE" >/dev/null 2>&1; then
    IMAGE_ID=$(docker inspect --format '{{.Image}}' "$IMAGE")
    IMAGE_CONTEXT="container $IMAGE"
else
    docker image inspect "$IMAGE" >/dev/null 2>&1 || {
        printf 'ERROR: image/container not found: %s\n' "$IMAGE" >&2
        exit 1
    }
    IMAGE_ID=$IMAGE
    IMAGE_CONTEXT="image $IMAGE"
fi

label() {
    docker image inspect --format "{{ index .Config.Labels \"$1\" }}" "$IMAGE_ID"
}

DESCRIPTION=$(label org.opencontainers.image.description)
printf 'Target: %s\n' "$IMAGE_CONTEXT"
printf 'Image ID: %s\n' "$(docker image inspect --format '{{.Id}}' "$IMAGE_ID")"
printf 'Tags: %s\n' "$(docker image inspect --format '{{.RepoTags}}' "$IMAGE_ID")"
printf 'Image size: %s bytes\n' "$(docker image inspect --format '{{.Size}}' "$IMAGE_ID")"
if [ -z "$DESCRIPTION" ] || [ "$DESCRIPTION" = '<no value>' ]; then
    printf 'Embedded description: none (existing image metadata is unchanged)\n'
    printf 'Image description: fixed InStock runtime base; update feature code through Git fast-forward or approved file sync in the existing /data/InStock path; do not rebuild this image for code-only releases.\n'
    printf 'Code path: /data/InStock root is not a bind mount; preserve the existing directory structure. Files under existing bind mounts update external storage; other code/Git writes may grow container SizeRw. Image size stays unchanged.\n'
    if [ "$IMAGE_CONTEXT" != "image $IMAGE" ]; then
        printf 'Container Git: '
        docker exec "$IMAGE" git --version
    fi
    printf 'Data policy: SQLite, application logs, caches, strategy state, and TDX files use the existing external mounts.\n'
    printf 'Current Docker stdout log cap: max-size=10m, max-file=2; this existing setting is not changed by code updates.\n'
    printf 'Size policy: keep this image unchanged for feature updates; container writable-layer growth per code update is limited to 64 MiB.\n'
    printf 'Persistent mounts: /data/InStock/instock/cache, /data/InStock/instock/core/strategy, /data/InStock/instock/forwardp, /data/InStock/instock/log\n'
else
    printf 'Title: %s\n' "$(label org.opencontainers.image.title)"
    printf 'Description: %s\n' "$DESCRIPTION"
    printf 'Release: %s\n' "$(label org.opencontainers.image.version)"
    printf 'Source revision: %s\n' "$(label org.opencontainers.image.revision)"
    printf 'Created: %s\n' "$(label org.opencontainers.image.created)"
    printf 'External data paths: %s\n' "$(label io.instock.external-data-paths)"
    printf 'Image size policy: %s\n' "$(label io.instock.image-size-policy)"
fi
