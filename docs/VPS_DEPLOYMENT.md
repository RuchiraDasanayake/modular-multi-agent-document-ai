# VPS Deployment Guide - Document AI

This guide walks you through deploying the Document AI system on a Linux VPS using Docker Compose.

**Estimated time: 30-45 minutes**

---

## 📋 Prerequisites

You'll need:

- A Linux VPS (Ubuntu 20.04+ or similar)
- SSH access to the VPS
- At least 8GB RAM, 4 CPU cores, 50GB disk space
- Domain name (optional - can use IP address)

**Recommended VPS providers:**

- DigitalOcean ($12-40/month)
- Linode ($12-96/month)
- AWS EC2 ($10-50/month)
- Vultr ($6-48/month)

---

## 🚀 Step 1: Prepare Your VPS

### 1.1 SSH into Your VPS

```bash
ssh root@YOUR_VPS_IP
```

### 1.2 Update System

```bash
apt-get update && apt-get upgrade -y
```

### 1.3 Install Docker

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Add current user to docker group (optional, allows non-root docker commands)
usermod -aG docker $USER
```

### 1.4 Install Docker Compose

```bash
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose
docker-compose --version
```

### 1.5 Install Python 3 and Git

```bash
apt-get install -y python3 python3-pip git
```

---

## 📦 Step 2: Clone and Prepare Repository

### 2.1 Clone the Repository

```bash
cd /opt  # or your preferred directory
git clone https://github.com/YOUR_ORG/modular-multi-agent-document-ai.git
cd modular-multi-agent-document-ai
git checkout feature/IDPO
```

### 2.2 Make Scripts Executable

```bash
chmod +x scripts/*.sh
```

### 2.3 Verify File Structure

```bash
ls -la
# You should see: docker-compose.prod.yml, .env.production, scripts/deploy-vps.sh
```

---

## 🔐 Step 3: Configure Secrets

### 3.1 Generate Secrets (on VPS)

```bash
python3 -c "import secrets; print('PostgreSQL Pass:', secrets.token_urlsafe(32))"
python3 -c "import secrets; print('Redis Pass:', secrets.token_urlsafe(32))"
python3 -c "import secrets; print('JWT Secret:', secrets.token_urlsafe(64))"
```

### 3.2 Edit Production Environment

```bash
nano .env.production
```

Replace these values with your generated secrets:

```bash
POSTGRES_PASSWORD=YOUR_GENERATED_POSTGRES_PASS
REDIS_PASSWORD=YOUR_GENERATED_REDIS_PASS
JWT_SECRET_KEY=YOUR_GENERATED_JWT_SECRET
NEXT_PUBLIC_API_URL=http://YOUR_VPS_IP:8000  # or https://your-domain.com
```

Press `Ctrl+X`, then `Y`, then `Enter` to save.

---

## 🚀 Step 4: Deploy Services

### 4.1 Build All Docker Images

```bash
docker-compose -f docker-compose.prod.yml build --no-cache
```

**⏱️ This takes 10-20 minutes on first run**

### 4.2 Start All Services

```bash
docker-compose -f docker-compose.prod.yml up -d
```

### 4.3 Verify Services Are Running

```bash
docker-compose -f docker-compose.prod.yml ps
```

You should see all services with status `Up` or `healthy`.

### 4.4 Check Logs

```bash
# View all logs
docker-compose -f docker-compose.prod.yml logs

# View specific service (e.g., frontend)
docker-compose -f docker-compose.prod.yml logs frontend

# Stream logs in real-time
docker-compose -f docker-compose.prod.yml logs -f
```

---

## ✅ Step 5: Verify Deployment

### 5.1 Test Frontend

```bash
curl -I http://YOUR_VPS_IP:3000
# Should return: HTTP/1.1 200 OK
```

### 5.2 Test API Gateway

```bash
curl -I http://YOUR_VPS_IP:8000/health
# Should return: HTTP/1.1 200 OK
```

### 5.3 Access in Browser

Open your browser and visit:

- **Frontend:** `http://YOUR_VPS_IP:3000`
- **API:** `http://YOUR_VPS_IP:8000`

---

## 🔒 Step 6: Optional - Set Up HTTPS with Let's Encrypt

### 6.1 Install Nginx + Certbot

```bash
apt-get install -y nginx certbot python3-certbot-nginx
```

### 6.2 Create Nginx Config

Create `/etc/nginx/sites-available/docai`:

```nginx
upstream frontend {
    server localhost:3000;
}

upstream api {
    server localhost:8000;
}

server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api {
        proxy_pass http://api;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 6.3 Enable Site and Get Certificate

```bash
ln -s /etc/nginx/sites-available/docai /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# Get SSL certificate (replace your-domain.com)
certbot --nginx -d your-domain.com
```

### 6.4 Update .env.production

```bash
NEXT_PUBLIC_API_URL=https://your-domain.com
```

### 6.5 Restart Services

```bash
docker-compose -f docker-compose.prod.yml restart
```

---

## 🛡️ Step 7: Firewall Configuration (Optional)

### 7.1 Configure UFW

```bash
ufw enable
ufw allow 22/tcp      # SSH
ufw allow 80/tcp      # HTTP
ufw allow 443/tcp     # HTTPS
ufw allow 3000/tcp    # Frontend (optional)
ufw allow 8000/tcp    # API (optional)
```

---

## 📊 Monitoring & Maintenance

### View Service Status

```bash
docker-compose -f docker-compose.prod.yml ps
```

### View Recent Logs

```bash
docker-compose -f docker-compose.prod.yml logs --tail=50 -f
```

### Stop Services

```bash
docker-compose -f docker-compose.prod.yml down
```

### Start Services (after stopping)

```bash
docker-compose -f docker-compose.prod.yml up -d
```

### View Resource Usage

```bash
docker stats
```

### Database Backup

```bash
docker-compose -f docker-compose.prod.yml exec db pg_dump -U produser ahmn_production > backup_$(date +%Y%m%d).sql
```

---

## 🔧 Troubleshooting

### Service Won't Start

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs SERVICE_NAME

# Rebuild
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d
```

### Port Already in Use

```bash
# Find what's using the port (example: port 3000)
lsof -i :3000

# Or stop conflicting service
docker-compose -f docker-compose.prod.yml down
```

### Out of Memory

Increase VPS memory or reduce resource limits in `docker-compose.prod.yml`:

```yaml
deploy:
  resources:
    limits:
      memory: 1g # Reduce this
      cpus: "0.5"
```

### Database Connection Issues

```bash
# Check database logs
docker-compose -f docker-compose.prod.yml logs db

# Verify connection
docker-compose -f docker-compose.prod.yml exec db psql -U produser -d ahmn_production -c "SELECT 1"
```

---

## 📈 Performance Tips

1. **Use SSD storage** for database and cache volumes
2. **Enable automatic backups** via your VPS provider
3. **Monitor resource usage** with `docker stats`
4. **Scale resources** based on document processing volume
5. **Set up log rotation** to prevent disk full issues

---

## 🆘 Quick Reference

| Task            | Command                                                                                              |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| Start services  | `docker-compose -f docker-compose.prod.yml up -d`                                                    |
| Stop services   | `docker-compose -f docker-compose.prod.yml down`                                                     |
| View logs       | `docker-compose -f docker-compose.prod.yml logs -f`                                                  |
| Rebuild         | `docker-compose -f docker-compose.prod.yml build --no-cache`                                         |
| Check health    | `bash scripts/check-health.sh`                                                                       |
| Database backup | `docker-compose -f docker-compose.prod.yml exec db pg_dump -U produser ahmn_production > backup.sql` |

---

## 🎯 After Deployment

1. ✅ Verify all services are accessible
2. ✅ Test document upload and extraction
3. ✅ Set up monitoring alerts
4. ✅ Configure automated backups
5. ✅ Document your setup for your team
6. ✅ Create a maintenance schedule

---

## 💬 Support

For issues or questions, check:

- Docker logs: `docker-compose -f docker-compose.prod.yml logs SERVICE_NAME`
- Service health: `docker-compose -f docker-compose.prod.yml ps`
- VPS system logs: `journalctl -xe`
