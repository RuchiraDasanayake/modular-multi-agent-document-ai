#!/bin/bash
# DocAI v2 Bootstrap - Minimal deployment script
# Run: bash bootstrap.sh

set -e
echo "[BOOTSTRAP] Starting DocAI v2 deployment..."

# === STEP 1: Create directories ===
echo "[1/7] Creating directories..."
sudo mkdir -p /opt/docai /var/lib/docai/db /var/lib/docai/runs /etc/docai
sudo chown -R ubuntu:ubuntu /opt/docai /var/lib/docai

# === STEP 2: Create docai system user ===
echo "[2/7] Creating docai system user..."
id docai &>/dev/null || sudo useradd -r -s /bin/false docai || true
sudo chown docai:docai /var/lib/docai /var/lib/docai/db /var/lib/docai/runs

# === STEP 3: Clone repo using HTTPS with fallback ===
echo "[3/7] Cloning DocAI repository..."
cd /opt/docai
rm -rf .git* 2>/dev/null || true
git init
git remote add origin https://github.com/ThimuthN/DocAi.git || git remote set-url origin https://github.com/ThimuthN/DocAi.git
git config --global http.postBuffer 524288000
git fetch --depth=1 origin c75ea4a || git fetch --depth=1 origin main || git fetch origin main
git checkout FETCH_HEAD 2>/dev/null || git checkout origin/main || echo "Git checkout completed"

# === STEP 4: Create Python venv and install ===
echo "[4/7] Setting up Python environment..."
python3 -m venv /opt/docai/.venv
/opt/docai/.venv/bin/python -m pip install --upgrade pip setuptools wheel 2>&1 | tail -5
/opt/docai/.venv/bin/python -m pip install -q -r /opt/docai/requirements.txt

# === STEP 5: Build frontend ===
echo "[5/7] Building frontend (this may take ~2-3 minutes)..."
cd /opt/docai/frontend
export VITE_DOCAI_API_BASE_URL=/api
npm ci --legacy-peer-deps --prefer-offline 2>&1 | grep -E "(added|up to date|error)" | head -3
npm run build 2>&1 | grep -E "(built|error)" | head -3

# === STEP 6: Configure backend env ===
echo "[6/7] Configuring backend..."
sudo cp /opt/docai/deploy/.env.backend.example /etc/docai/docai-backend.env
sudo sed -i "s|https://your-frontend.example.com|http://$(hostname -I | awk '{print $1}')|g" /etc/docai/docai-backend.env
sudo chown docai:docai /etc/docai/docai-backend.env

# === STEP 7: Setup systemd ===
echo "[7/7] Installing systemd service..."
sudo sed 's|User=docai|User=ubuntu|g' /opt/docai/deploy/systemd/docai-backend.service | sudo tee /etc/systemd/system/docai-backend.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable docai-backend

# === FINAL: Start and validate ===
echo "[FINAL] Starting backend service..."
sudo systemctl start docai-backend
sleep 2
sudo systemctl status docai-backend --no-pager || true

echo ""
echo "=== BOOTSTRAP COMPLETE ==="
echo "Backend: http://127.0.0.1:8000"
echo "Frontend: http://$(hostname -I | awk '{print $1}')/"
echo ""
echo "Health check:"
curl -s http://127.0.0.1:8000/health || echo "Backend not responding yet"
echo ""
