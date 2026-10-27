#!/bin/sh
# Gera config.js com a URL da API a partir da variável de ambiente API_URL.
set -eu
: "${API_URL:=http://localhost:8000}"
cat > /usr/share/nginx/html/config.js <<JS
window.APP_CONFIG = { apiUrl: "${API_URL}" };
JS
echo "config.js gerado com apiUrl=${API_URL}"
