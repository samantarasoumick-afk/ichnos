# DatFe frontend (Next.js).
#
# Build: docker build -t datafe-frontend ./frontend
# Run:   see docker-compose.yml at the repo root - this image expects
#        BACKEND_INTERNAL_URL at runtime (where the Next.js server
#        proxies /backend/* requests to the FastAPI backend).

FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# Next.js resolves next.config.ts's rewrites() (and therefore
# BACKEND_INTERNAL_URL) at `next build` time, not at container start -
# so the runtime-only `environment:` value in docker-compose.yml is
# too late by itself. Accepting it as a build arg here and exporting
# it as an env var before the build step makes sure the same value
# ends up baked into both the build and the running container.
ARG BACKEND_INTERNAL_URL=http://backend:8000
ENV BACKEND_INTERNAL_URL=$BACKEND_INTERNAL_URL

RUN npm run build

FROM node:20-slim

WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/package.json /app/package-lock.json* ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./next.config.ts

EXPOSE 3000

CMD ["npm", "run", "start"]
