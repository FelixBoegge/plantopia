# syntax=docker/dockerfile:1

# Builder: produce the static build. Node only exists in this stage — the runtime image
# below is Caddy alone.
FROM node:22-slim AS builder

WORKDIR /app

# package.json/package-lock.json first so this layer only rebuilds on a dependency change,
# not on every source edit.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Runtime: Caddy serving the static build and reverse-proxying /api/** to the API's own
# Cloud Run service — the same origin the browser sees, which is what the refresh cookie's
# SameSite=Strict and the client's relative /api/v1 base path both require.
FROM caddy:2-alpine

COPY --from=builder /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
