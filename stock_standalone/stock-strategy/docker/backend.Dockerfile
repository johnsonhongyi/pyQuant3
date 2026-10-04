FROM debian:bookworm-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates tzdata wget libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 stockstrategy \
    && useradd --system --uid 10001 --gid stockstrategy --no-create-home --shell /usr/sbin/nologin stockstrategy

WORKDIR /app
COPY --chown=10001:10001 easy-stock-backend /app/easy-stock-backend
RUN chmod 0755 /app/easy-stock-backend

ENV TZ=Asia/Hong_Kong
EXPOSE 20081
USER 10001:10001
ENTRYPOINT ["/app/easy-stock-backend"]
