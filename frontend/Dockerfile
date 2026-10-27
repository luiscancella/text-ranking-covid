FROM nginx:alpine

ENV API_URL=http://localhost:8000

COPY index.html /index.html

# Substitui a variável API_URL no HTML na hora de subir o container
CMD ["/bin/sh", "-c", "envsubst '$API_URL' < /index.html > /usr/share/nginx/html/index.html && nginx -g 'daemon off;'"]
