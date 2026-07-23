# Ichnos frontend (Next.js).
#
# Build: docker build -t ichnos-frontend ./frontend
# Run:   see docker-compose.yml at the repo root - this image expects
#        BACKEND_INTERNAL_URL at runtime (where the Next.js server
#        proxies /backend/* requests to the FastAPI backend).

FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .
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
