# syntax=docker/dockerfile:1.7

FROM node:22-slim AS frontend-deps
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm install

FROM frontend-deps AS frontend-build
ARG VITE_APP_BASE_URL
ARG VITE_UPLOAD_FUNCTION_URL
ARG VITE_SENTRY_DSN
ARG VITE_SENTRY_ENVIRONMENT
ENV VITE_APP_BASE_URL=${VITE_APP_BASE_URL}
ENV VITE_UPLOAD_FUNCTION_URL=${VITE_UPLOAD_FUNCTION_URL}
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN}
ENV VITE_SENTRY_ENVIRONMENT=${VITE_SENTRY_ENVIRONMENT}
COPY frontend ./
RUN npm run build

FROM node:22-slim AS server-deps
WORKDIR /app/server
COPY server/package*.json ./
RUN --mount=type=cache,target=/root/.npm npm install

FROM server-deps AS server-build
COPY server ./
RUN npm run build && npm prune --omit=dev

FROM node:22-slim AS runtime
WORKDIR /app/server
ENV NODE_ENV=production
ENV FRONTEND_DIST_PATH=/app/frontend/dist
COPY --from=server-build /app/server/package*.json ./
COPY --from=server-build /app/server/node_modules ./node_modules
COPY --from=server-build /app/server/dist ./dist
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist
EXPOSE 8080
CMD ["node", "dist/index.js"]
