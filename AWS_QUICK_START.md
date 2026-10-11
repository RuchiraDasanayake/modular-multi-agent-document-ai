# Legacy AWS quick reference

The instance and zero-cost claims below have not been validated for the current
five-service product stack. Use the
[current single-host deployment path](docs/DEPLOYMENT_CURRENT.md) and obtain a
current provider quote before provisioning.

## 🎯 5-Minute AWS Setup (No Coding Required!)

### Step 1: Create AWS Account

- Go to https://aws.amazon.com/free
- Sign up (free for 12 months)
- Add payment method (won't charge you)

### Step 2: Launch EC2 Instance

1. Log in to AWS Console: https://console.aws.amazon.com
2. Search for **EC2** in the search bar
3. Click **Instances** → **Launch Instances**
4. **Name**: `DocumentAI`
5. **AMI**: Select `Ubuntu Server 22.04 LTS`
6. **Instance Type**: `t2.micro` ← **Must be this (free tier)**
7. **Key Pair**: Click "Create new key pair"
   - Name: `docai-key`
   - Format: `.pem` (Mac/Linux) or `.ppk` (Windows)
   - Download it! (You'll need this to connect)
8. **Security Group**: Create new
   - Add inbound rules for ports: **22, 80, 443, 3000, 8000**
   - Source: `0.0.0.0/0` (anywhere)
9. **Storage**: 30GB (maximum free tier)
10. Click **Launch Instances**

### Step 3: Get Your IP Address

1. Wait 2-3 minutes for instance to start
2. Go to **EC2 → Instances**
3. Click on your instance
4. Copy the **Public IPv4 address** (e.g., `12.34.56.78`)

### Step 4: Connect via SSH

**On Mac/Linux:**

```bash
chmod 400 ~/Downloads/docai-key.pem
ssh -i ~/Downloads/docai-key.pem ubuntu@YOUR_PUBLIC_IP
```

**On Windows:** Use PuTTY (convert `.pem` to `.ppk` with PuTTYgen)

### Step 5: Deploy Application

Once connected, run:

```bash
curl -O https://raw.githubusercontent.com/YOUR_ORG/modular-multi-agent-document-ai/feature/IDPO/scripts/vps-setup.sh
sudo bash vps-setup.sh

# Save the secrets it outputs!

cd /opt
git clone https://github.com/YOUR_ORG/modular-multi-agent-document-ai.git
cd modular-multi-agent-document-ai
git checkout feature/IDPO

nano .env.production
# Edit with your secrets and IP

docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d
```

### Step 6: Access Your Application

```
http://YOUR_PUBLIC_IP:3000      (Frontend)
http://YOUR_PUBLIC_IP:8000      (API)
```

---

## ✅ AWS Free Tier Limits

| Service        | Limit           | Your Usage        |
| -------------- | --------------- | ----------------- |
| EC2 (t2.micro) | 750 hours/month | ✓ One instance    |
| Storage (EBS)  | 30 GB           | ✓ 30 GB allocated |
| Data Transfer  | 100 GB/month    | ✓ Modest usage    |
| **TOTAL COST** | **$0/month**    | **FREE**          |

⚠️ **Stay within limits or you'll be charged!**

---

## 🔐 Security Tips

1. **Change SSH source to your IP only** (not 0.0.0.0/0)
2. **Enable AWS Budgets** → Set $1 alert
3. **Save your key pair** somewhere safe
4. **Never share** your `.pem` file

---

## 🛠️ Quick Commands (via SSH)

```bash
# Check if running
docker-compose -f docker-compose.prod.yml ps

# View logs
docker-compose -f docker-compose.prod.yml logs -f

# Stop services
docker-compose -f docker-compose.prod.yml down

# Restart services
docker-compose -f docker-compose.prod.yml restart
```

---

## 💾 Stop Instance (Save $$$ when not in use)

Via AWS Console:

1. **EC2 → Instances**
2. Right-click instance
3. **Instance State → Stop** (NOT Terminate)
4. When done, click **Start** to resume

**Stopping = no charges!**

---

## 📖 Full Guide

See `docs/AWS_FREE_TIER_SETUP.md` for complete instructions with screenshots.

---

## 🆘 Common Issues

| Problem              | Solution                                             |
| -------------------- | ---------------------------------------------------- |
| Can't SSH            | Check Security Group port 22 is open                 |
| Instance won't start | Wait 2-3 min, then refresh AWS Console               |
| Out of free tier     | Stop instance immediately, check billing             |
| Port already in use  | Run `docker-compose -f docker-compose.prod.yml down` |

---

**Total Setup Time: ~20 minutes**
**Total Cost: FREE (12 months)**

🚀 You're ready to deploy!
