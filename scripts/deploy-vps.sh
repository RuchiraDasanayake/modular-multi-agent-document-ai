#!/bin/bash
# Production Deployment Script for VPS
# Usage: bash scripts/deploy-vps.sh your-domain.com YOUR_VPS_IP

set -e

DOMAIN="${1:-localhost}"
VPS_IP="${2:-$(hostname -I | awk '{print $1}')}"

echo "================================================================"
echo "  Document AI Production Deployment"
echo "================================================================"
echo ""
echo "Domain: $DOMAIN"
echo "VPS IP: $VPS_IP"
echo ""

# Check prerequisites
echo "[*] Checking prerequisites..."
if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed. Install it first:"
    echo "        curl -fsSL https://get.docker.com -o get-docker.sh && sh get-docker.sh"
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "[ERROR] Docker Compose is not installed."
    exit 1
fi

echo "[OK] Docker and Docker Compose found"
echo ""

# Generate secure secrets
echo "[*] Generating secure secrets..."
POSTGRES_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
REDIS_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")

echo "[OK] Secrets generated"
echo ""

# Determine API URL
if [ "$DOMAIN" == "localhost" ]; then
    API_URL="http://$VPS_IP:8000"
else
    API_URL="https://$DOMAIN"
fi

# Update .env.production with actual values
echo "[*] Configuring .env.production..."
cp .env.production .env.production.tmp

sed -i.bak \
    -e "s|POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$POSTGRES_PASS|" \
    -e "s|REDIS_PASSWORD=.*|REDIS_PASSWORD=$REDIS_PASS|" \
    -e "s|JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$JWT_SECRET|" \
    -e "s|NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=$API_URL|" \
    .env.production

echo "[OK] Configuration updated"
echo ""

# Load environment
export $(cat .env.production | grep -v '#' | xargs)

# Build services
echo "[*] Building Docker images (this may take 10-15 minutes)..."
docker-compose -f docker-compose.prod.yml build --no-cache
echo "[OK] Build complete"
echo ""

# Start services
echo "[*] Starting services..."
docker-compose -f docker-compose.prod.yml up -d

echo "[OK] Services started"
echo ""

# Wait for health checks
echo "[*] Waiting for services to be healthy (max 3 minutes)..."
RETRIES=0
MAX_RETRIES=36

while [ $RETRIES -lt $MAX_RETRIES ]; do
    if docker-compose -f docker-compose.prod.yml ps | grep -q "healthy"; then
        echo "[OK] Services healthy"
        break
    fi
    echo "[*] Waiting... ($RETRIES/$MAX_RETRIES)"
    sleep 5
    RETRIES=$((RETRIES + 1))
done

if [ $RETRIES -eq $MAX_RETRIES ]; then
    echo "[WARN] Services did not reach healthy state. Checking logs..."
    docker-compose -f docker-compose.prod.yml logs --tail=50
fi

echo ""
echo "================================================================"
echo "  Deployment Complete!"
echo "================================================================"
echo ""
echo "Access your application:"
echo ""
if [ "$DOMAIN" == "localhost" ]; then
    echo "   Frontend:  http://$VPS_IP:3000"
    echo "   API:       http://$VPS_IP:8000"
else
    echo "   Frontend:  https://$DOMAIN"
    echo "   API:       https://$DOMAIN/api"
fi
echo ""
echo "Production Secrets:"
echo "   - Database password: (saved in .env.production)"
echo "   - Redis password: (saved in .env.production)"
echo "   - JWT secret: (saved in .env.production)"
echo ""
echo "Next Steps:"
echo "   1. Set up SSL/TLS with Let's Encrypt + Nginx (optional)"
echo "   2. Configure firewall rules"
echo "   3. Monitor logs: docker-compose -f docker-compose.prod.yml logs -f"
echo "   4. Create backups of .env.production and database volumes"
echo ""
echo "To stop services:"
echo "   docker-compose -f docker-compose.prod.yml down"
echo ""
