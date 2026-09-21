# Build context: apps/web (app Angular autonoma, no depende de packages/core
# ni del workspace de uv - a diferencia de apps/api/Dockerfile no hace falta
# construir desde la raiz del repo).
FROM node:20-alpine AS builder
WORKDIR /app

RUN corepack enable

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# Salida real de `ng build` en este scaffold (Angular 21, sin SSR/prerender):
# dist/claude-export-md-web/browser/ - confirmado contra un build local, no
# supuesto (ver STATUS.md M4).
FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist/claude-export-md-web/browser /usr/share/nginx/html

EXPOSE 80
