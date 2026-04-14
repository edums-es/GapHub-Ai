FROM node:20-alpine AS builder

WORKDIR /app

ARG REACT_APP_BACKEND_URL=http://localhost:8000
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL

COPY package*.json yarn.lock* ./
RUN yarn install --frozen-lockfile 2>/dev/null || npm ci

COPY . .
RUN npm run build 2>/dev/null || yarn build

# ── Produção com Nginx ─────────────────────────────────────────────────────
FROM nginx:alpine

COPY --from=builder /app/build /usr/share/nginx/html

# Configuração Nginx para SPA (React Router)
RUN echo 'server { \
    listen 80; \
    root /usr/share/nginx/html; \
    index index.html; \
    location / { try_files $uri $uri/ /index.html; } \
    location /api { proxy_pass http://backend:8000; proxy_set_header Host $host; } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
