FROM nginx:stable-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY web-entrypoint.sh /usr/local/bin/stockstrategy-entrypoint
RUN chmod 0755 /usr/local/bin/stockstrategy-entrypoint

ENTRYPOINT ["/usr/local/bin/stockstrategy-entrypoint"]
