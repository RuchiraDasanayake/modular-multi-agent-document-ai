FROM node:20-alpine AS deps
LABEL stage=deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps || npm install --legacy-peer-deps

FROM node:20-alpine AS builder
RUN apk update && apk upgrade
LABEL stage=builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Build-time env for Next.js (baked into client bundle)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Internal API URL for server-side rewrites (baked at build time)
ARG INTERNAL_API_URL=http://gateway:8000
ENV INTERNAL_API_URL=$INTERNAL_API_URL

RUN npm run build

FROM node:20-alpine AS runner
RUN apk update && apk upgrade && apk add --no-cache dumb-init
LABEL maintainer="Modular Document AI Frontend"
LABEL description="Next.js frontend for Modular Document AI platform"
WORKDIR /app
ENV NODE_ENV=production
USER node

# Copy built application
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=10s --start-period=30s --retries=8 \
    CMD node -e "require('http').get('http://localhost:3000',(r)=>{process.exit(r.statusCode<400?0:1)}).on('error',()=>process.exit(1))"

CMD ["node", "server.js"]
