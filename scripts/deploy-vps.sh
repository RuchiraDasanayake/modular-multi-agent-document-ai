#!/usr/bin/env bash
# Deploy the default five-service product stack on a Linux host.
# Usage: bash scripts/deploy-vps.sh PUBLIC_HOST_OR_IP

set -euo pipefail

PUBLIC_HOST="${1:?Usage: bash scripts/deploy-vps.sh PUBLIC_HOST_OR_IP}"
if [[ ! "$PUBLIC_HOST" =~ ^[[:alnum:]][[:alnum:].-]*$ ]]; then
    echo "PUBLIC_HOST_OR_IP must be a DNS name or IPv4 address." >&2
    exit 1
fi
cd "$(dirname "${BASH_SOURCE[0]}")/.."

if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo "Docker with the Compose plugin is required." >&2
    exit 1
fi

if [[ ! -f .env.production ]]; then
    if ! command -v python3 >/dev/null 2>&1; then
        echo "Python 3 is required to generate initial secrets." >&2
        exit 1
    fi
    umask 077
    postgres_password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    redis_password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    jwt_secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
    admin_password="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
    temporary_env="$(mktemp .env.production.XXXXXX)"
    trap 'rm -f "$temporary_env"' EXIT
    cat > "$temporary_env" <<EOF
# Generated once by scripts/deploy-vps.sh. Back up this file securely.
POSTGRES_USER=user
POSTGRES_PASSWORD=${postgres_password}
POSTGRES_DB=ahmn_db
REDIS_PASSWORD=${redis_password}
JWT_SECRET_KEY=${jwt_secret}
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@localhost
ADMIN_PASSWORD=${admin_password}
NEXT_PUBLIC_API_URL=http://${PUBLIC_HOST}:8000
BACKEND_CORS_ORIGINS=http://${PUBLIC_HOST}:3000
EOF
    mv "$temporary_env" .env.production
    trap - EXIT
    echo "Created .env.production with new credentials. Save the first admin password from that file securely."
fi

chmod 600 .env.production
# A caller's shell variables otherwise take precedence over --env-file.
unset POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB REDIS_PASSWORD JWT_SECRET_KEY
unset ADMIN_USERNAME ADMIN_EMAIL ADMIN_PASSWORD NEXT_PUBLIC_API_URL BACKEND_CORS_ORIGINS
unset PUBLIC_SIGNUP_ENABLED ICORE_API_KEY IDPO_AUTO_MODEL IDPO_AUTO_API_BASE_URL
compose=(docker compose --env-file .env.production -f docker-compose.prod.yml)
"${compose[@]}" config --quiet
"${compose[@]}" build
"${compose[@]}" up -d --wait --wait-timeout 180

echo "Product stack is healthy. Frontend: http://${PUBLIC_HOST}:3000"
echo "API health: http://${PUBLIC_HOST}:8000/health"
echo "Configure TLS and a reverse proxy before exposing this deployment to untrusted networks."
