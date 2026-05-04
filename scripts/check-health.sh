#!/bin/bash
# Quick health check for deployed services

echo "Checking service health..."
echo ""

SERVICES=(
    "Frontend:3000"
    "Gateway:8000"
    "AHMN:8001"
    "Guardrails:8002"
    "XAI-HITL:8003"
    "IDPO:8004"
)

for service in "${SERVICES[@]}"; do
    NAME="${service%:*}"
    PORT="${service#*:}"
    
    if curl -s "http://localhost:$PORT/health" > /dev/null 2>&1; then
        echo "[OK] $NAME (port $PORT) - Healthy"
    else
        echo "[DOWN] $NAME (port $PORT) - Down"
    fi
done

echo ""
echo "Container Status:"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "Recent Logs (last 20 lines):"
docker-compose -f docker-compose.prod.yml logs --tail=20
