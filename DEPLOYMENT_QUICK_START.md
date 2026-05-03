# 🚀 QUICK START - Deploy in 30 Minutes

## 📋 Pre-Flight Checklist

- [ ] VPS provisioned (Ubuntu 20.04+, 8GB RAM, 4 CPU, 50GB disk)
- [ ] SSH access to VPS working
- [ ] Domain name ready (optional - can use IP)
- [ ] This repository cloned locally

## 🎯 The 5-Step Plan

### STEP 1: Set Up VPS (5 minutes)

```bash
# SSH into VPS
ssh root@YOUR_VPS_IP

# Run setup script (installs Docker, Docker Compose, Python)
curl -O https://raw.githubusercontent.com/YOUR_ORG/modular-multi-agent-document-ai/feature/IDPO/scripts/vps-setup.sh
bash vps-setup.sh

# Save the secrets it outputs!
```

**Output to save:**

- PostgreSQL Password
- Redis Password
- JWT Secret

---

### STEP 2: Clone Repository (2 minutes)

```bash
cd /opt
git clone https://github.com/YOUR_ORG/modular-multi-agent-document-ai.git
cd modular-multi-agent-document-ai
git checkout feature/IDPO
```

---

### STEP 3: Configure Secrets (3 minutes)

```bash
# Edit production environment
nano .env.production

# Replace these with saved secrets:
# POSTGRES_PASSWORD=YOUR_SAVED_POSTGRES_PASS
# REDIS_PASSWORD=YOUR_SAVED_REDIS_PASS
# JWT_SECRET_KEY=YOUR_SAVED_JWT_SECRET
# NEXT_PUBLIC_API_URL=http://YOUR_VPS_IP:8000

# Save: Ctrl+X → Y → Enter
```

---

### STEP 4: Deploy Services (15 minutes)

```bash
# Build all Docker images (first time only - takes ~15 min)
docker-compose -f docker-compose.prod.yml build --no-cache

# Start all services
docker-compose -f docker-compose.prod.yml up -d

# Monitor startup
docker-compose -f docker-compose.prod.yml logs -f

# Wait for all services to show "healthy" status
# (Ctrl+C to exit logs when everything is running)
```

---

### STEP 5: Verify & Access (5 minutes)

```bash
# Check all services running
docker-compose -f docker-compose.prod.yml ps
# All should show "Up" or "healthy"

# Quick health check
curl http://localhost:3000      # Frontend
curl http://localhost:8000      # API

# Or access in browser:
# http://YOUR_VPS_IP:3000       (Frontend)
# http://YOUR_VPS_IP:8000       (API)
```

---

## ✅ You're Live!

Your document AI system is now running on the VPS!

**Access it:**

- 🌐 Frontend: `http://YOUR_VPS_IP:3000`
- 🔌 API: `http://YOUR_VPS_IP:8000`

---

## 📊 Common Commands

```bash
# View status
docker-compose -f docker-compose.prod.yml ps

# View logs (real-time)
docker-compose -f docker-compose.prod.yml logs -f

# View specific service logs
docker-compose -f docker-compose.prod.yml logs frontend

# Stop services
docker-compose -f docker-compose.prod.yml down

# Restart services
docker-compose -f docker-compose.prod.yml restart

# Check resource usage
docker stats
```

---

## 🔒 Optional: HTTPS Setup (10 minutes extra)

If you have a domain and want HTTPS:

```bash
# Install Nginx + Let's Encrypt
apt-get install -y nginx certbot python3-certbot-nginx

# Get certificate (replace your-domain.com)
certbot --nginx -d your-domain.com

# Update .env.production
nano .env.production
# Change: NEXT_PUBLIC_API_URL=https://your-domain.com

# Restart
docker-compose -f docker-compose.prod.yml restart
```

See `docs/VPS_DEPLOYMENT.md` for full HTTPS setup.

---

## 🆘 Troubleshooting

**Services not starting?**

```bash
# Check logs
docker-compose -f docker-compose.prod.yml logs

# Rebuild
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d
```

**Port already in use?**

```bash
# Stop all services
docker-compose -f docker-compose.prod.yml down

# Start again
docker-compose -f docker-compose.prod.yml up -d
```

**Stuck on building?**

```bash
# Check Docker daemon
docker ps

# Or rebuild without cache
docker-compose -f docker-compose.prod.yml build --no-cache --pull
```

---

## 📞 Support

- Full guide: `docs/VPS_DEPLOYMENT.md`
- Health check script: `bash scripts/check-health.sh`
- Contact your VPS provider for infrastructure issues

---

**Total Time to Production: ~30 minutes** ⏱️
