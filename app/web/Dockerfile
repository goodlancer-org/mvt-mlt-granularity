# GEOMAPS Web UI
# Multi-stage: build React app with Node, serve with Caddy

# ── Stage 1: Build ───────────────────────────────────────────────────
FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . .
RUN npm run build

# ── Stage 2: Serve ───────────────────────────────────────────────────
FROM caddy:2-alpine

# Copy built React app
COPY --from=build /app/dist /srv/app

# Copy Caddy configuration
COPY Caddyfile /etc/caddy/Caddyfile

EXPOSE 80
