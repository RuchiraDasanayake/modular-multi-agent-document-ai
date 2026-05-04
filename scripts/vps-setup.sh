#!/bin/bash
# VPS Setup - One-time preparation script
# Run this ONCE after SSHing into your VPS

set -e

echo "================================================================"
echo "  Document AI - VPS Initial Setup"
echo "================================================================"
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "[ERROR] This script must be run as root"
    echo "        Use: sudo bash scripts/vps-setup.sh"
    exit 1
fi

# Step 1: Update System
echo "[*] Step 1: Updating system packages..."
apt-get update > /dev/null 2>&1
apt-get upgrade -y > /dev/null 2>&1
echo "[OK] System updated"

# Step 2: Install Docker
echo "[*] Step 2: Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh > /dev/null 2>&1
    sh get-docker.sh > /dev/null 2>&1
    echo "[OK] Docker installed"
else
    echo "[OK] Docker already installed"
fi

# Step 3: Install Docker Compose
echo "[*] Step 3: Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE_VERSION=$(curl -s https://api.github.com/repos/docker/compose/releases/latest | grep 'tag_name' | cut -d'"' -f4)
    curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose > /dev/null 2>&1
    chmod +x /usr/local/bin/docker-compose
    echo "[OK] Docker Compose installed"
else
    echo "[OK] Docker Compose already installed"
fi

# Step 4: Install Python
echo "[*] Step 4: Installing Python..."
apt-get install -y python3 python3-pip > /dev/null 2>&1
echo "[OK] Python installed"

# Step 5: Install Git
echo "[*] Step 5: Installing Git..."
apt-get install -y git > /dev/null 2>&1
echo "[OK] Git installed"

# Step 6: Generate Secrets
echo ""
echo "[*] Generating production secrets..."
POSTGRES_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
REDIS_PASS=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(64))")

echo ""
echo "================================================================"
echo "  VPS Setup Complete!"
echo "================================================================"
echo ""
echo "SAVE THESE SECRETS (you'll need them in next step):"
echo ""
echo "PostgreSQL Password:"
echo "  $POSTGRES_PASS"
echo ""
echo "Redis Password:"
echo "  $REDIS_PASS"
echo ""
echo "JWT Secret:"
echo "  $JWT_SECRET"
echo ""
echo "================================================================"
echo ""
echo "[OK] Docker: $(docker --version)"
echo "[OK] Docker Compose: $(docker-compose --version)"
echo "[OK] Python: $(python3 --version)"
echo "[OK] Git: $(git --version)"
echo ""
echo "Next steps:"
echo "1. Clone the repository:"
echo "   cd /opt && git clone https://github.com/YOUR_ORG/modular-multi-agent-document-ai.git"
echo "   cd modular-multi-agent-document-ai && git checkout feature/IDPO"
echo ""
echo "2. Edit .env.production with secrets above:"
echo "   nano .env.production"
echo ""
echo "3. Run deployment:"
echo "   bash scripts/deploy-vps.sh your-domain.com"
echo ""
echo "4. Monitor progress:"
echo "   docker-compose -f docker-compose.prod.yml logs -f"
echo ""
