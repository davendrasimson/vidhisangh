# syntax=docker/dockerfile:1.7
# ════════════════════════════════════════════════════════════════════
#  VidhiSangh — Frontend (Angular 21) image
#  Multi-stage:  dev  |  build → prod (nginx)
#  Build dev :  docker build --target dev  -t vidhisangh-frontend:dev  .
#  Build prod:  docker build --target prod -t vidhisangh-frontend:prod .
#
#  Base images are pinned by digest (multi-arch index, resolved 2026-09-27;
#  the tag is kept in the comment so Dependabot/renovate can bump both).
#  Node 22 LTS is the minimum for Angular 21 (20.19+/22.12+).
# ════════════════════════════════════════════════════════════════════

# ─── dev ────────────────────────────────────────────────────────────
# node:22-alpine
FROM node:26-alpine@sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5 AS dev
WORKDIR /app
ENV NPM_CONFIG_UPDATE_NOTIFIER=false NPM_CONFIG_FUND=false NPM_CONFIG_AUDIT=false

# Cached dependency layer — only re-runs when the lockfile changes.
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
USER node
EXPOSE 4200
CMD ["npm", "start", "--", "--host", "0.0.0.0"]

# ─── build ──────────────────────────────────────────────────────────
# node:22-alpine
FROM node:26-alpine@sha256:6bd9ab43c0ec0190ca7b2d193906cb8b7edf6e7f4afa43ddeccd6452710bffb5 AS build
WORKDIR /app
ENV NPM_CONFIG_UPDATE_NOTIFIER=false NPM_CONFIG_FUND=false NPM_CONFIG_AUDIT=false

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

# ─── prod ───────────────────────────────────────────────────────────
# Static assets served by nginx as the unprivileged `nginx` user on :8080
# with a read-only root filesystem: every path nginx writes is redirected
# to /tmp (mounted as an emptyDir in Kubernetes).
# nginx:1.27-alpine
FROM nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 AS prod

RUN apk add --no-cache curl \
    && rm -f /etc/nginx/conf.d/default.conf \
    # Drop the `user` directive (we run as nginx already) and move the pid
    # and every temp/cache path under /tmp so `/` can be read-only.
    && sed -i '/^user\s*nginx;/d' /etc/nginx/nginx.conf \
    && sed -i 's,/var/run/nginx.pid,/tmp/nginx.pid,' /etc/nginx/nginx.conf \
    && sed -i 's,^http {,http {\n    client_body_temp_path /tmp/client_temp;\n    proxy_temp_path       /tmp/proxy_temp;\n    fastcgi_temp_path     /tmp/fastcgi_temp;\n    uwsgi_temp_path       /tmp/uwsgi_temp;\n    scgi_temp_path        /tmp/scgi_temp;\n    server_tokens off;,' /etc/nginx/nginx.conf

# SPA server config (SPA fallback, gzip, caching, security headers, API proxy).
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Built Angular bundle.
COPY --from=build --chown=nginx:nginx /app/dist/vidhisangh/browser /usr/share/nginx/html

USER nginx
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://localhost:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
