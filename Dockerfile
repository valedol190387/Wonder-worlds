# Планета монстриков — один процесс Node без зависимостей.
# node:sqlite нужен Node 22.13+ (в 22-alpine он есть).
FROM node:22-alpine

WORKDIR /app
COPY . .

ENV NODE_ENV=production \
    PORT=8123 \
    DATA_DIR=/data

# сюда Coolify/Docker монтирует постоянный том: база + монстрики + фоны
VOLUME ["/data"]
EXPOSE 8123

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8123/health || exit 1

CMD ["node", "--no-warnings", "server.js"]
