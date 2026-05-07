#!/bin/bash
# DocAI Alpha Deployment Script
# Usage: ./deploy.sh <oracle-vm-public-ip> [username]
#
# Example:
#   ./deploy.sh 140.238.123.45 ubuntu
#   ./deploy.sh 140.238.123.45
#
# Uses SSH keys from:
#   ~/.ssh/oracle-key (private)
#   ~/.ssh/oracle-key.pub (public, for reference)

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <oracle-vm-public-ip> [username]"
  echo "Example: $0 140.238.123.45 ubuntu"
  exit 1
fi

ORACLE_IP=$1
ORACLE_USER=${2:-ubuntu}
SSH_KEY="${HOME}/.ssh/oracle-key"

echo "==================================================================="
echo "DocAI Alpha Deployment"
echo "==================================================================="
echo "Target: $ORACLE_USER@$ORACLE_IP"
echo "SSH Key: $SSH_KEY"
echo ""

# Verify SSH key exists
if [ ! -f "$SSH_KEY" ]; then
  echo "[ERROR] SSH key not found: $SSH_KEY"
  echo "Copy the key to ~/.ssh/oracle-key and chmod 600"
  exit 1
fi

# Check SSH connectivity
echo "[1/9] Testing SSH connectivity..."
if ! ssh -i "$SSH_KEY" -o ConnectTimeout=5 "$ORACLE_USER@$ORACLE_IP" "echo OK" > /dev/null 2>&1; then
  echo "[ERROR] Cannot SSH to $ORACLE_IP with key $SSH_KEY"
  echo "Check:"
  echo "  1. Oracle VM is running"
  echo "  2. Security list allows port 22 from your IP"
  echo "  3. SSH key is correct"
  echo "  4. Username is correct (usually 'ubuntu' for Oracle Linux images)"
  exit 1
fi
echo "[✓] SSH connection successful"
echo ""

# Deploy function - runs all commands on remote VM
deploy_commands="
set -e

echo '[2/9] Updating system packages...'
sudo apt-get update > /dev/null 2>&1
sudo apt-get upgrade -y > /dev/null 2>&1

echo '[3/9] Installing dependencies...'
sudo apt-get install -y \
  python3.11 python3.11-venv python3-pip \
  git nginx tesseract-ocr nodejs npm \
  curl ufw apache2-utils > /dev/null 2>&1

echo '[4/9] Cloning repository...'
if [ ! -d /opt/docai ]; then
  sudo git clone https://github.com/yourusername/docai /opt/docai
else
  cd /opt/docai && sudo git pull
fi

echo '[5/9] Setting up backend...'
cd /opt/docai
sudo python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt > /dev/null 2>&1
deactivate

echo '[6/9] Building frontend...'
cd frontend
VITE_DOCAI_API_BASE_URL=/api npm run build > /dev/null 2>&1
cd ..

echo '[7/9] Creating data directories...'
sudo mkdir -p /var/lib/docai/{runs,uploads}
sudo useradd -s /bin/false -d /opt/docai docai 2>/dev/null || true
sudo chown -R docai:docai /opt/docai /var/lib/docai
sudo chmod -R 755 /var/lib/docai

echo '[8/9] Setting up services...'
sudo cp deploy/docai.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable docai
sudo systemctl start docai

sudo cp deploy/nginx.docai.conf /etc/nginx/sites-available/docai
sudo rm /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo ln -s /etc/nginx/sites-available/docai /etc/nginx/sites-enabled/docai
sudo nginx -t
sudo systemctl reload nginx

echo '[9/9] Setting up firewall and auth...'
echo 'alpha' | sudo htpasswd -c /etc/nginx/.docai_htpasswd -i alpha
sudo chown www-data:www-data /etc/nginx/.docai_htpasswd
sudo chmod 640 /etc/nginx/.docai_htpasswd

sudo sed -i 's/# auth_basic/auth_basic/' /etc/nginx/sites-available/docai
sudo sed -i 's/# auth_basic_user_file/auth_basic_user_file/' /etc/nginx/sites-available/docai
sudo nginx -t && sudo systemctl reload nginx

sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw --force enable

echo ''
echo '=========================================='
echo 'Deployment complete!'
echo '=========================================='
echo \"Backend service status:\"
sudo systemctl status docai --no-pager || true
echo ''
echo \"Access the application at:\"
echo \"  http://$HOSTNAME/\"
echo \"  Username: alpha\"
echo \"  Password: alpha\"
echo ''
echo \"Health check:\"
echo \"  curl -u alpha:alpha http://127.0.0.1/api/health\"
"

echo "[Starting remote deployment...]"
echo ""

ssh -i "$SSH_KEY" "$ORACLE_USER@$ORACLE_IP" "$deploy_commands"

echo ""
echo "[Deployment complete!]"
echo ""
echo "==================================================================="
echo "POST-DEPLOYMENT STEPS"
echo "==================================================================="
echo ""
echo "1. Verify deployment (from your laptop):"
echo "   curl -u alpha:alpha http://$ORACLE_IP/api/health"
echo ""
echo "2. Open in browser:"
echo "   http://$ORACLE_IP/"
echo "   Username: alpha"
echo "   Password: alpha"
echo ""
echo "3. Test workflow:"
echo "   - Create project"
echo "   - Create extraction profile"
echo "   - Create job"
echo "   - Upload test document"
echo "   - Execute run"
echo "   - Verify extraction results"
echo ""
echo "4. Monitor logs:"
echo "   ssh -i $SSH_KEY $ORACLE_USER@$ORACLE_IP"
echo "   sudo journalctl -u docai -f"
echo ""
echo "==================================================================="
