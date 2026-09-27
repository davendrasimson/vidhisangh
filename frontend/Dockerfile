# syntax=docker/dockerfile:1.7
# ════════════════════════════════════════════════════════════════════
#  VidhiSangh — Frontend (Angular 21) image
#  Multi-stage:  dev  |  build → prod (nginx)
#  Build dev :  docker build --target dev  -t vidhisangh-frontend:dev  .
#  Build prod:  docker build --target prod -t vidhisangh-frontend:prod .
# ════════════════════════════════════════════════════════════════════

# ─── dev ────────────────────────────────────────────────────────────
# Angular CLI dev server with HMR. Source is bind-mounted by
# docker-compose; deps are baked so the container is usable standalone.
FROM node:20-alpine AS dev
WORKDIR /app

# Cached dependency layer — only re-runs when the manifest/lockfile change.
COPY package*.json ./
RUN npm ci

COPY . .

EXPOSE 4200
CMD ["npm", "start", "--", "--host", "0.0.0.0"]

# ─── build ──────────────────────────────────────────────────────────
# Produces the optimized static bundle in dist/vidhisangh/browser.
FROM node:20-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ─── prod ───────────────────────────────────────────────────────────
# Static assets served by nginx, hardened to run as the unprivileged
# `nginx` user on port 8080 (no root, no privileged ports).
FROM nginx:1.27-alpine AS prod

RUN apk add --no-cache curl \
    # Serve on a non-privileged port and let the nginx user own runtime paths.
    && sed -i 's,listen\s*80;,listen 8080;,'            /etc/nginx/conf.d/default.conf 2>/dev/null || true \
    && sed -i '/^user\s*nginx;/d'                       /etc/nginx/nginx.conf \
    && sed -i 's,/var/run/nginx.pid,/tmp/nginx.pid,'    /etc/nginx/nginx.conf

# SPA server config (SPA fallback, gzip, caching, security headers, API proxy).
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Built Angular bundle.
COPY --from=build /app/dist/vidhisangh/browser /usr/share/nginx/html

# Make runtime paths writable by the unprivileged user.
RUN chown -R nginx:nginx /usr/share/nginx/html /var/cache/nginx \
    && touch /tmp/nginx.pid && chown nginx:nginx /tmp/nginx.pid

USER nginx

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
