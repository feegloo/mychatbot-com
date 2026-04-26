FROM node:22-slim AS frontend
WORKDIR /app/frontend

ARG VITE_APP_BASE_URL
ARG VITE_UPLOAD_FUNCTION_URL
ARG VITE_SENTRY_DSN
ARG VITE_SENTRY_ENVIRONMENT

ENV VITE_APP_BASE_URL=${VITE_APP_BASE_URL}
ENV VITE_UPLOAD_FUNCTION_URL=${VITE_UPLOAD_FUNCTION_URL}
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN}
ENV VITE_SENTRY_ENVIRONMENT=${VITE_SENTRY_ENVIRONMENT}

COPY frontend/package*.json ./
RUN npm install
COPY frontend ./
RUN npm run build

FROM node:22-slim AS server
WORKDIR /app/server
ENV NODE_ENV=production
COPY server/package*.json ./
RUN npm install
COPY server ./
RUN npm run build && npm prune --omit=dev
COPY --from=frontend /app/frontend/dist /app/frontend/dist
ENV FRONTEND_DIST_PATH=/app/frontend/dist
EXPOSE 8080
CMD ["npm", "start"]
