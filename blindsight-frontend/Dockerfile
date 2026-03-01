# ── Stage 1: install dependencies ─────────────────────────────────────────────
FROM node:22-alpine AS deps

WORKDIR /app

COPY package.json package-lock.json .npmrc ./
RUN npm ci --legacy-peer-deps

# ── Stage 2: build ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS builder

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build args become public env vars baked into the JS bundle at build time
ARG NEXT_PUBLIC_STREAM_API_KEY
ENV NEXT_PUBLIC_STREAM_API_KEY=$NEXT_PUBLIC_STREAM_API_KEY

RUN npm run build

# ── Stage 3: production runtime ────────────────────────────────────────────────
FROM node:22-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000

# Non-root user
RUN addgroup -S nextjs && adduser -S nextjs -G nextjs

COPY --from=builder /app/public* ./public/
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
