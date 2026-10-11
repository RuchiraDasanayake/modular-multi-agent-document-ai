# Legacy AWS deployment guide

The instance and zero-cost claims below have not been validated for the current
five-service product stack. Use the
[current single-host deployment path](DEPLOYMENT_CURRENT.md) and obtain a
current provider quote before provisioning.

Your Document AI application is ready for production deployment on AWS. **Total cost: $0 for 12 months.**

---

## 📊 Overview

| Item                       | Details                         |
| -------------------------- | ------------------------------- |
| **Cloud Provider**         | AWS (Amazon Web Services)       |
| **Instance Type**          | t2.micro (1 vCPU, 1GB RAM)      |
| **OS**                     | Ubuntu 22.04 LTS                |
| **Storage**                | 30GB SSD                        |
| **Cost (12 months)**       | **FREE** ✅                     |
| **Cost (after 12 months)** | ~$12/month (t2.micro + storage) |
| **Total Setup Time**       | ~50 minutes                     |

---

## 🗂️ What's Been Created For You

### Documentation Files

1. **`AWS_QUICK_START.md`** ← Start here! (5-min reference)
2. **`docs/AWS_FREE_TIER_SETUP.md`** (Complete 40-page guide with screenshots)
3. **`DEPLOYMENT_QUICK_START.md`** (Deployment overview)

### Script Files

1. **`scripts/aws-setup-wizard.sh`** - Interactive step-by-step setup
2. **`scripts/aws-launch-ec2.sh`** - Automated EC2 launcher (requires AWS CLI)
3. **`scripts/vps-setup.sh`** - Prepares VPS (generates secrets, installs Docker)
4. **`scripts/deploy-vps.sh`** - Deploys Docker containers

### Configuration Files

1. **`docker-compose.prod.yml`** - Production Docker Compose config
2. **`.env.production`** - Environment template (EDIT THIS with secrets)

---

## 🎯 Quick Path to Deployment

### Option A: Manual Setup (Recommended for First Time)

**Time: ~50 minutes | Difficulty: Easy**

```bash
# 1. Follow AWS_QUICK_START.md sections 1-4 (20 minutes)
#    - Create AWS account
#    - Launch EC2 instance
#    - Get IP address
#    - Connect via SSH

# 2. SSH into your instance, then run:
curl -O https://raw.githubusercontent.com/YOUR_ORG/modular-multi-agent-document-ai/feature/IDPO/scripts/vps-setup.sh
sudo bash vps-setup.sh

# 3. Save the 3 secrets it outputs!

# 4. Clone and deploy:
cd /opt
sudo git clone https://github.com/YOUR_ORG/modular-multi-agent-document-ai.git
cd modular-multi-agent-document-ai && git checkout feature/IDPO

nano .env.production
# Edit with your secrets and IP

docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d

# 5. Access at: http://YOUR_IP:3000
```

---

### Option B: Interactive Wizard (Guided)

**Time: ~50 minutes | Difficulty: Very Easy**

```bash
# Run this from your repo on your LOCAL machine (not AWS)
bash scripts/aws-setup-wizard.sh

# It will guide you through every step with checkboxes
```

---

### Option C: Automated (AWS CLI Required)

**Time: ~30 minutes | Difficulty: Advanced**

Prerequisites: AWS CLI installed and configured

```bash
# Generate EC2 instance automatically
bash scripts/aws-launch-ec2.sh

# Then follow manual deployment steps
```

---

## 📋 Complete Step-by-Step (Manual)

### PHASE 1: Create AWS Account (5 min)

1. Go to https://aws.amazon.com/free
2. Click "Create a free account"
3. Fill out sign-up form
4. Add payment method (won't charge you)
5. Verify email and phone
6. Select "Basic (Free)" plan

### PHASE 2: Launch EC2 Instance (10 min)

1. Log into https://console.aws.amazon.com
2. Search for **EC2** → Click EC2
3. Click **Instances** → **Launch Instances**

**Fill these out:**

- Name: `DocumentAI`
- AMI: `Ubuntu Server 22.04 LTS`
- Instance Type: `t2.micro` (MUST be this!)
- Key Pair: Click "Create new"
  - Name: `docai-key`
  - Format: `.pem` (Mac/Linux) or `.ppk` (Windows)
  - **Download and save it!**
- Security Group: Create new `docai-sg`
  - Add inbound rules for ports: 22, 80, 443, 3000, 8000
  - Source: 0.0.0.0/0 (anywhere)
- Storage: 30GB gp2

4. Click **Launch Instances**
5. Wait 2-3 minutes for instance to start

### PHASE 3: Get Public IP (2 min)

1. Go to EC2 → Instances
2. Click your instance
3. Copy the **Public IPv4 address** (e.g., `12.34.56.78`)

### PHASE 4: Connect via SSH (2 min)

**On Mac/Linux:**

```bash
chmod 400 ~/Downloads/docai-key.pem
ssh -i ~/Downloads/docai-key.pem ubuntu@YOUR_PUBLIC_IP
```

**On Windows:**

- Use PuTTY with converted `.ppk` key
- See docs/AWS_FREE_TIER_SETUP.md for details

### PHASE 5: Deploy Application (30 min)

Once SSH'd into your instance:

```bash
# Install Docker and generate secrets
curl -O https://raw.githubusercontent.com/YOUR_ORG/modular-multi-agent-document-ai/feature/IDPO/scripts/vps-setup.sh
sudo bash vps-setup.sh

# SAVE THE SECRETS! You'll need them next

# Clone repository
cd /opt
sudo git clone https://github.com/YOUR_ORG/modular-multi-agent-document-ai.git
cd modular-multi-agent-document-ai
git checkout feature/IDPO

# Configure environment
nano .env.production

# Replace these:
# POSTGRES_PASSWORD=<from-vps-setup>
# REDIS_PASSWORD=<from-vps-setup>
# JWT_SECRET_KEY=<from-vps-setup>
# NEXT_PUBLIC_API_URL=http://YOUR_PUBLIC_IP:8000

# Build and deploy
docker-compose -f docker-compose.prod.yml build --no-cache
# ⏱️ Takes ~15 minutes...

docker-compose -f docker-compose.prod.yml up -d

# Monitor startup
docker-compose -f docker-compose.prod.yml logs -f
# When all services are "healthy", press Ctrl+C
```

### PHASE 6: Access Your App (1 min)

Open your browser:

- **Frontend:** http://YOUR_PUBLIC_IP:3000
- **API:** http://YOUR_PUBLIC_IP:8000

✅ **You're live!**

---

## 🔐 AWS Free Tier Limits

⚠️ **STAY WITHIN THESE LIMITS OR YOU'LL BE CHARGED:**

| Service        | Free Tier Limit | Your Usage | Status      |
| -------------- | --------------- | ---------- | ----------- |
| EC2 (t2.micro) | 750 hours/month | 1 instance | ✅ OK       |
| EBS Storage    | 30 GB/month     | 30 GB      | ✅ OK       |
| Data Transfer  | 100 GB/month    | ~10-20 GB  | ✅ OK       |
| **Total Cost** | **$0**          | **$0**     | ✅ **FREE** |

**After 12 months:** ~$12-15/month if you keep it running

---

## 💾 Managing Your Instance

### Stop Instance (Save Money When Not Using)

```
AWS Console → EC2 → Instances
Right-click → Instance State → Stop

# When you want to use it again:
Right-click → Instance State → Start
```

⚠️ **Note:** Stopping = no charges for compute, but storage still costs ~$0.10/month

### Restart Services

```bash
ssh -i ~/Downloads/docai-key.pem ubuntu@YOUR_PUBLIC_IP

docker-compose -f docker-compose.prod.yml restart
```

### Monitor Logs

```bash
docker-compose -f docker-compose.prod.yml logs -f
docker-compose -f docker-compose.prod.yml logs frontend
```

### Stop Everything

```bash
docker-compose -f docker-compose.prod.yml down
```

---

## 🔒 Security Recommendations

1. **Restrict SSH to Your IP Only:**
   - AWS Console → EC2 → Security Groups
   - Edit `docai-sg` inbound rules
   - Change SSH source from `0.0.0.0/0` to your IP only
   - Find your IP: https://www.whatsmyipaddress.com

2. **Enable AWS Budgets Alert:**
   - AWS Console → Billing → Budgets
   - Create $1/month budget alert
   - You'll be notified if charges are about to happen

3. **Backup Your Key:**
   - Save `docai-key.pem` somewhere secure
   - Never commit to git
   - Never share with anyone

4. **Monitor Usage:**
   - Regularly check AWS Console → Billing Dashboard
   - Free Tier tab shows current usage

---

## 📊 Performance Expectations

**t2.micro Specs:**

- CPU: 1 vCPU (burstable)
- RAM: 1 GB
- Network: Low to moderate

**Realistic:**

- ✅ Good for: demos, testing, light production use
- ✅ Handles: 5-10 concurrent users
- ✅ Document processing: 5-20 docs/hour
- ⚠️ If you scale: upgrade to t2.small (~$20/mo) or t3.small (~$10/mo)

---

## 🔧 Troubleshooting

### Can't SSH

```bash
# Check security group
# AWS Console → EC2 → Security Groups → docai-sg
# Should have inbound SSH rule on port 22

# Check key permissions
chmod 400 ~/Downloads/docai-key.pem

# Verbose connection
ssh -v -i ~/Downloads/docai-key.pem ubuntu@YOUR_PUBLIC_IP
```

### Instance Won't Start

```bash
# Wait 2-3 minutes
# Refresh AWS Console
# Check system log:
# Right-click instance → Monitor and troubleshoot → System log
```

### Docker Build Fails

```bash
# Check disk space
df -h

# Rebuild
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml build --no-cache
```

### Out of Free Tier

```bash
# STOP THE INSTANCE IMMEDIATELY
# AWS Console → EC2 → Instances
# Right-click → Instance State → Stop

# Check billing
# AWS Console → Billing Dashboard → Bills

# Contact AWS support to request credit
```

---

## 📖 Documentation Guides

| Document                        | Purpose                            |
| ------------------------------- | ---------------------------------- |
| **AWS_QUICK_START.md**          | 5-minute quick reference           |
| **docs/AWS_FREE_TIER_SETUP.md** | Complete detailed guide (40 pages) |
| **DEPLOYMENT_QUICK_START.md**   | General deployment overview        |
| **docs/VPS_DEPLOYMENT.md**      | VPS admin and maintenance          |
| **docs/SYSTEM_CONTRACT.md**     | System architecture and runtime    |

---

## 🎯 What To Do Next

1. ✅ Create AWS account (5 min)
2. ✅ Launch EC2 instance (10 min)
3. ✅ Connect via SSH (2 min)
4. ✅ Run deployment (30 min)
5. ✅ Test application (5 min)
6. ✅ Enable AWS Budget alert (2 min)
7. ✅ Document your setup (save secrets somewhere safe!)

**Total: ~55 minutes to production** 🚀

---

## 💬 Getting Help

**If stuck, check:**

1. `docs/AWS_FREE_TIER_SETUP.md` for detailed instructions
2. AWS Console → Instance → System Logs
3. `docker-compose -f docker-compose.prod.yml logs` for app issues
4. AWS Support: https://console.aws.amazon.com/support

**Common errors:**

- "Permission denied (publickey)" → Check key permissions with `chmod 400`
- "Cannot connect to instance" → Check security group has port 22 open
- "Out of disk space" → Increase EBS volume size or clean up Docker images

---

## ✨ After Deployment

1. Test uploading a document via the UI
2. Monitor application for 24 hours
3. Set up automated backups
4. Configure monitoring alerts
5. Share the public IP with your team
6. Document your AWS setup for your team

---

## 🎉 You're Ready!

**Everything is set up for deployment. Follow the step-by-step guide above and you'll be live on AWS within an hour.**

### Quick Summary:

- 📝 AWS Account: 5 min (one-time)
- 🖥️ EC2 Instance: 10 min (one-time)
- 🔑 SSH Key: 2 min (one-time)
- 🚀 Deploy App: 30 min (reusable)
- 💰 **Cost: $0 for 12 months, then ~$12/month**

**Let's deploy! 🚀**

---

For the most up-to-date information and troubleshooting, see `docs/AWS_FREE_TIER_SETUP.md`.
