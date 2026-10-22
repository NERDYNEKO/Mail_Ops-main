# ---- build client ----
FROM node:22-alpine AS client
WORKDIR /client
COPY client/package*.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

# ---- build server ----
FROM node:22-alpine AS server
WORKDIR /server
COPY server/package*.json ./
RUN npm ci
COPY server/ ./
RUN npm run build && npm prune --omit=dev

# ---- runtime ----
FROM node:22-alpine
RUN apk add --no-cache chromium font-noto
ENV NODE_ENV=production CHROME_PATH=/usr/bin/chromium ASSETS_DIR=/app/assets CLIENT_DIR=/app/client PORT=8080
WORKDIR /app/server
COPY --from=server /server/node_modules ./node_modules
COPY --from=server /server/dist ./dist
COPY --from=server /server/package.json ./
COPY --from=client /client/dist /app/client
COPY assets /app/assets
USER node
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:8080/api/healthz || exit 1
CMD ["node", "dist/index.js"]
