FROM debian:bookworm-slim

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ca-certificates tzdata wget libsqlite3-0 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 stockstrategy \
    && useradd --system --uid 10001 --gid stockstrategy --no-create-home --shell /usr/sbin/nologin stockstrategy

WORKDIR /app
ENV TZ=Asia/Hong_Kong
EXPOSE 20081
USER 10001:10001
LABEL io.easy-stock.managed=stockstrategy \
      io.easy-stock.runtime-base=stockstrategy \
      io.easy-stock.runtime-version=base-v1
