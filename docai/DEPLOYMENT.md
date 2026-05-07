# DocAI Alpha Deployment Guide

Public deployment on Oracle Cloud VM with Nginx reverse proxy and Basic Auth.

## Prerequisites

- Oracle Cloud VM (Ubuntu 22.04 LTS recommended)
- 4GB RAM, 30GB disk
- Public IP address
- SSH access

## Step 1: VM Setup

```bash
# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Install required packages
sudo apt-get install -y \
  python3.11 \
  python3.11-venv \
  python3-pip \
  git \
  nginx \
  tesseract-ocr \
  nodejs \
  npm \
  curl \
  ufw \
  apache2-utils

# Verify installations
python3.11 --version
node --version
tesseract --version
```

## Step 2: Clone and Setup Backend

```bash
# Clone repository
git clone <repo-url> /opt/docai
cd /opt/docai

# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt

# Verify key packages
python -c "import fastapi; import pymupdf; print('OK')"

# Deactivate venv (systemd will activate)
deactivate
```

## Step 3: Create Persistent Data Directories

```bash
# Create directories
sudo mkdir -p /var/lib/docai/runs
sudo mkdir -p /var/lib/docai/uploads

# Set permissions
sudo chown -R docai:docai /var/lib/docai
sudo chmod -R 755 /var/lib/docai

# Verify
ls -ld /var/lib/docai/*
```

## Step 4: Build Frontend with Public API Base URL

```bash
cd /opt/docai/frontend

# Copy production environment
cp ../deploy/.env.production .env.production

# Build with API base URL set to /api
VITE_DOCAI_API_BASE_URL=/api npm run build

# Verify dist exists
ls -la dist/ | head -5
```

## Step 5: Setup Systemd Service

```bash
# Copy service file
sudo cp deploy/docai.service /etc/systemd/system/

# Create docai user
sudo useradd -s /bin/false -d /opt/docai docai

# Fix ownership
sudo chown -R docai:docai /opt/docai
sudo chown -R docai:docai /var/lib/docai

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable docai
sudo systemctl start docai

# Verify service is running
sudo systemctl status docai

# Check logs
sudo journalctl -u docai -n 20
```

## Step 6: Configure Nginx

```bash
# Copy Nginx config
sudo cp deploy/nginx.docai.conf /etc/nginx/sites-available/docai

# Enable site (disable default if needed)
sudo ln -s /etc/nginx/sites-available/docai /etc/nginx/sites-enabled/
sudo rm /etc/nginx/sites-enabled/default 2>/dev/null || true

# Test Nginx config
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx
```

## Step 7: Setup Basic Auth (Required for Public Alpha)

```bash
# Create auth file
sudo htpasswd -c /etc/nginx/.docai_htpasswd alpha

# When prompted, enter password (e.g., "alpha123")

# Fix ownership
sudo chown www-data:www-data /etc/nginx/.docai_htpasswd
sudo chmod 640 /etc/nginx/.docai_htpasswd

# Uncomment auth lines in /etc/nginx/sites-available/docai
sudo sed -i 's/# auth_basic/auth_basic/' /etc/nginx/sites-available/docai
sudo sed -i 's/# auth_basic_user_file/auth_basic_user_file/' /etc/nginx/sites-available/docai

# Reload Nginx
sudo nginx -t && sudo systemctl reload nginx
```

## Step 8: Configure Firewall

```bash
# Enable UFW
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow "Nginx Full"
sudo ufw enable

# Verify rules
sudo ufw status

# Expected output:
# 22/tcp (OpenSSH) - ALLOW IN
# 80/tcp (Nginx Full) - ALLOW IN
# 443/tcp (Nginx Full) - ALLOW IN
```

## Step 9: Smoke Test (Public)

From your own laptop (not VM):

```bash
# Get public IP
ORACLE_IP=<your-oracle-vm-public-ip>

# 1. Test backend health
curl -u alpha:alpha123 http://$ORACLE_IP/api/health

# Expected response:
# {"status":"ok","service":"docai-v2-api"}

# 2. Open frontend in browser
# http://$ORACLE_IP/

# 3. Browser test:
# - Login with username: alpha, password: alpha123
# - Create project
# - Create extraction profile  
# - Create job
# - Upload test document (image/PDF/TXT)
# - Execute run
# - Verify final_output appears
# - Save review correction
# - Refresh page - review history should persist

# 4. Test restart persistence
# SSH into VM:
ssh ubuntu@$ORACLE_IP

# Restart backend
sudo systemctl restart docai

# Wait 5 seconds
sleep 5

# Verify service is running
sudo systemctl status docai

# Back in browser:
# - Refresh page
# - All previous data should still exist (projects, jobs, runs, reviews)
```

## Nginx Configuration Details

The Nginx config file (`deploy/nginx.docai.conf`) does:

1. **Frontend serving** (root `/opt/docai/frontend/dist`):
   - Serves `index.html` for any path not found
   - Enables SPA routing

2. **API reverse proxy** (`/api/` → `http://127.0.0.1:8000/`):
   - Trailing slashes ensure `/api/health` becomes `/health` at backend
   - Preserves original request headers for proper logging
   - 300s timeout for long extraction jobs
   - Disabled buffering for streaming

3. **Security**:
   - Backend NOT exposed publicly (127.0.0.1:8000)
   - Frontend NOT exposed on 5173
   - Only 80/443 (Nginx) are public
   - Basic Auth gates all access

## Frontend API Configuration

The frontend reads `VITE_DOCAI_API_BASE_URL` from:
1. Build-time environment variable (highest priority)
2. Default fallback: `http://localhost:8000` (dev only)

For public deployment, build with:
```bash
VITE_DOCAI_API_BASE_URL=/api npm run build
```

This makes the frontend call `http://<public-ip>/api/...` through Nginx.

## Database and Artifacts

All persistent data is stored in `/var/lib/docai/`:

```
/var/lib/docai/
├── docai.sqlite         - Projects, jobs, runs, documents, reviews
└── runs/
    ├── run-123/         - Run artifacts
    │   ├── final_output.json
    │   ├── validation_report.json
    │   └── artifacts/
    └── run-456/
```

These are mounted as persistent volumes on Oracle VM.

## Monitoring

```bash
# View service logs in real-time
sudo journalctl -u docai -f

# View last 50 lines
sudo journalctl -u docai -n 50

# View Nginx error log
sudo tail -f /var/log/nginx/error.log

# View Nginx access log
sudo tail -f /var/log/nginx/access.log

# Check systemd service status
sudo systemctl status docai

# Check database file
ls -lh /var/lib/docai/docai.sqlite

# Check disk usage
du -sh /var/lib/docai/
```

## Troubleshooting

### Backend not responding

```bash
# Check service status
sudo systemctl status docai

# Check logs
sudo journalctl -u docai -n 30

# Restart service
sudo systemctl restart docai

# Verify socket is bound
sudo netstat -tlnp | grep 8000
```

### Frontend not loading

```bash
# Check Nginx status
sudo systemctl status nginx

# Check Nginx config
sudo nginx -t

# Check file permissions
ls -la /opt/docai/frontend/dist/

# Check Nginx logs
sudo tail -f /var/log/nginx/error.log
```

### API calls failing from frontend

```bash
# Verify API base URL is set correctly in built frontend
# Edit /opt/docai/frontend/dist/index.html
# Search for "VITE_DOCAI_API_BASE_URL" or "/api"

# Rebuild with correct env var
cd /opt/docai/frontend
VITE_DOCAI_API_BASE_URL=/api npm run build
sudo systemctl reload nginx
```

### Upload failures

```bash
# Check max upload size in Nginx config
grep client_max_body_size /etc/nginx/sites-enabled/docai
# Should be: client_max_body_size 52M;

# Check backend setting
grep DOCAI_MAX_UPLOAD_BYTES /etc/systemd/system/docai.service
# Should be: 52428800 bytes = 50 MB

# Check disk space
df -h /var/lib/docai/
```

## HTTPS (Optional, Recommended for Production)

Use Let's Encrypt with Certbot:

```bash
# Install Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# Obtain certificate (replace yourdomain.com)
sudo certbot certonly --standalone -d yourdomain.com

# Update Nginx to use HTTPS
sudo vim /etc/nginx/sites-available/docai

# Add:
# listen 443 ssl http2;
# ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
# ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
# 
# Redirect HTTP to HTTPS:
# server {
#     listen 80;
#     return 301 https://$host$request_uri;
# }

# Test and reload
sudo nginx -t && sudo systemctl reload nginx

# Auto-renewal
sudo systemctl enable certbot.timer
```

## Backup Strategy

Backup `/var/lib/docai/docai.sqlite` regularly:

```bash
# Daily backup
sudo cp /var/lib/docai/docai.sqlite /opt/backups/docai.sqlite.$(date +%Y%m%d-%H%M%S)

# Verify backup
ls -la /opt/backups/ | head -5
```

## Deployment Checklist

- [ ] VM provisioned on Oracle Cloud
- [ ] Python 3.11+ installed
- [ ] Node 18+ installed
- [ ] Tesseract OCR installed
- [ ] Nginx installed
- [ ] Repository cloned to `/opt/docai`
- [ ] Virtual environment created and dependencies installed
- [ ] Persistent directories created (`/var/lib/docai/*`)
- [ ] Frontend built with `VITE_DOCAI_API_BASE_URL=/api`
- [ ] Systemd service file installed and enabled
- [ ] Nginx config installed and enabled
- [ ] UFW firewall configured (allow 22, 80, 443 only)
- [ ] Basic Auth configured
- [ ] Service started and verified working
- [ ] Backend health check passes: `/api/health`
- [ ] Frontend loads and can create project
- [ ] Document upload works
- [ ] Run execution works
- [ ] Review persistence works
- [ ] Service restart persistence verified

---

**Deploy Status**: Ready for alpha public deployment

**Public URL Pattern**: `http://<oracle-vm-public-ip>/` (with Basic Auth)

**Backend (private)**: `http://127.0.0.1:8000` (not publicly exposed)

**Support Contact**: For issues, check journalctl logs and Nginx error logs.
