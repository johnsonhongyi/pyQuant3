ARG BACKEND_RUNTIME_IMAGE
FROM golang:1.26-alpine AS builder

ENV GOMAXPROCS=1 GOGC=50 GOMEMLIMIT=600MiB GOPROXY=https://goproxy.cn,direct
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN mkdir -p /out && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/easy-stock-backend ./cmd/server

FROM ${BACKEND_RUNTIME_IMAGE}
COPY --from=builder --chown=10001:10001 /out/easy-stock-backend /app/easy-stock-backend
RUN chmod 0755 /app/easy-stock-backend
ENTRYPOINT ["/app/easy-stock-backend"]
