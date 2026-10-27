FROM nginx:1.27-alpine

COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.d/40-app-config.sh /docker-entrypoint.d/40-app-config.sh
COPY public/ /usr/share/nginx/html/

RUN chmod +x /docker-entrypoint.d/40-app-config.sh

ENV API_URL=http://localhost:8000

EXPOSE 80
