# syntax=docker/dockerfile:1

# EmeHub frontend.
#
# Stage 1 builds the Vite/React SPA; stage 2 serves the static bundle with nginx
# on :5180. nginx also reverse-proxies the same-origin /api path to the api
# container (nginx.conf), so the whole app is one origin — like the dev proxy.
FROM node:20-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 5180
