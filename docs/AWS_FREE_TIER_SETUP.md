# Legacy AWS free tier setup guide

The instance and zero-cost claims below have not been validated for the current
five-service product stack. Use the
[current single-host deployment path](DEPLOYMENT_CURRENT.md) and obtain a
current provider quote before provisioning.

**Total Cost: FREE (for 12 months)**
**Time: 15-20 minutes**

This guide walks you through setting up a free AWS EC2 instance to host your Document AI system.

---

## 📋 Prerequisites

- AWS Account (create at https://aws.amazon.com/free)
- Valid credit card (for verification - won't be charged during free tier)
- SSH client (built-in on Mac/Linux, use PuTTY on Windows)

---

## ✅ Step 1: Create AWS Account (5 minutes)

### 1.1 Sign Up

1. Go to https://aws.amazon.com/free
2. Click **"Create a free account"**
3. Enter your email, password, and account name
4. Add your payment method (won't be charged during free tier)
5. Verify your phone number
6. Choose the **Basic (Free)** plan

### 1.2 Verify Email

You'll receive a verification email. Click the link to confirm.

---

## 🖥️ Step 2: Launch EC2 Instance (10 minutes)

### 2.1 Log Into AWS Console

1. Go to https://console.aws.amazon.com
2. Sign in with your account
3. Search for **"EC2"** in the search bar at the top
4. Click **EC2** under "Services"

### 2.2 Launch Instance

**From the EC2 Dashboard:**

1. Click **"Instances"** in the left sidebar
2. Click **"Launch Instances"** (orange button)

**Configuration:**

#### **Name and tags:**

- Name: `DocumentAI`

#### **Application and OS Images (AMI):**

- Select **"Ubuntu"**
- Choose: **Ubuntu Server 22.04 LTS (Free tier eligible)**
- Architecture: **64-bit (x86)**

#### **Instance type:**

- Select: **`t2.micro`** (eligible for free tier ✓)
- This gives you 1 vCPU, 1 GB RAM (sufficient for demo)

#### **Key pair (login):**

This is CRITICAL - you need this to SSH in!

1. Click **"Create new key pair"**
2. Name: `docai-key`
3. Key pair type: **RSA**
4. Private key format: **`.pem`** (Mac/Linux) or **`.ppk`** (Windows/PuTTY)
5. Click **"Create key pair"**
6. A file `docai-key.pem` will download to your computer
   - **SAVE THIS SOMEWHERE SAFE** - you won't get it again!
   - On Mac: Move it to `~/.ssh/docai-key.pem`

#### **Network settings:**

1. VPC: Keep default
2. Subnet: Keep default
3. **Auto-assign public IP:** Select **"Enable"** ✓
4. Create security group: **Create new security group**
   - Name: `docai-sg`
   - Description: `Security group for Document AI`

#### **Inbound Security Group Rules:**

Add these rules by clicking "Add security group rule":

| Type       | Port | Source               |
| ---------- | ---- | -------------------- |
| SSH        | 22   | 0.0.0.0/0 (Anywhere) |
| HTTP       | 80   | 0.0.0.0/0 (Anywhere) |
| HTTPS      | 443  | 0.0.0.0/0 (Anywhere) |
| Custom TCP | 3000 | 0.0.0.0/0 (Anywhere) |
| Custom TCP | 8000 | 0.0.0.0/0 (Anywhere) |

#### **Storage:**

- Size: **30 GB** (free tier allows up to 30GB)
- Type: **gp2 (General Purpose)**
- Keep remaining defaults

#### **Advanced details:**

Leave as defaults

### 2.3 Launch

1. Review all settings
2. Click **"Launch Instance"** (orange button)
3. Wait for the instance to start (1-2 minutes)

---

## 🔑 Step 3: Get Your Public IP Address (2 minutes)

1. Go back to **EC2 Dashboard** → **Instances**
2. Click on your instance (`DocumentAI`)
3. Look for **"Public IPv4 address"** in the details
4. Copy it (e.g., `12.34.56.78`)

**Save this IP - you'll use it to connect!**

---

## 🔐 Step 4: Connect via SSH (5 minutes)

### 4.1 On Mac/Linux:

```bash
# Make key readable
chmod 400 ~/Downloads/docai-key.pem

# Connect to your instance
ssh -i ~/Downloads/docai-key.pem ubuntu@YOUR_PUBLIC_IP

# Example:
# ssh -i ~/Downloads/docai-key.pem ubuntu@12.34.56.78
```

### 4.2 On Windows with PuTTY:

1. Download PuTTYgen from https://www.putty.org
2. Convert your `.pem` key:
   - Open PuTTYgen
   - Click "Load" → Select `docai-key.pem`
   - Click "Save private key" → Save as `docai-key.ppk`
3. Open PuTTY
   - Host: `ubuntu@YOUR_PUBLIC_IP` (e.g., `ubuntu@12.34.56.78`)
   - Connection → SSH → Auth → Private key file → Select `docai-key.ppk`
   - Click "Open"

### 4.3 First Connection

When you first connect, you may see:

```
The authenticity of host can't be established...
Are you sure you want to continue connecting (yes/no)?
```

Type `yes` and press Enter.

You should now see:

```
ubuntu@ip-172-31-xxx-xxx:~$
```

✅ **You're in your AWS EC2 instance!**

---

## 🎯 Step 5: Deploy Document AI (30 minutes)

Now you can follow the deployment guide:

```bash
# Run VPS setup (generates secrets)
curl -O https://raw.githubusercontent.com/YOUR_ORG/modular-multi-agent-document-ai/feature/IDPO/scripts/vps-setup.sh
sudo bash vps-setup.sh

# It will output 3 secrets - SAVE THEM!
# - PostgreSQL Password
# - Redis Password
# - JWT Secret
```

Then continue with:

```bash
cd /opt
git clone https://github.com/YOUR_ORG/modular-multi-agent-document-ai.git
cd modular-multi-agent-document-ai
git checkout feature/IDPO

# Edit .env.production with your secrets
nano .env.production

# Then deploy
docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d

# Check status
docker-compose -f docker-compose.prod.yml ps
```

See `DEPLOYMENT_QUICK_START.md` for full deployment steps.

---

## 🌐 Step 6: Access Your Application

Once deployed, access it at:

```
http://YOUR_PUBLIC_IP:3000      (Frontend)
http://YOUR_PUBLIC_IP:8000      (API)
```

Example:

```
http://12.34.56.78:3000
http://12.34.56.78:8000
```

---

## ⚠️ AWS Free Tier Limits

Make sure you stay within free tier:

| Service        | Free Tier Limit | Your Usage     |
| -------------- | --------------- | -------------- |
| EC2            | 750 hours/month | ✓ One t2.micro |
| Storage (EBS)  | 30 GB/month     | ✓ 30 GB disk   |
| Data transfer  | 100 GB/month    | ✓ Modest usage |
| **Total Cost** | **$0**          | **FREE**       |

⚠️ **If you exceed limits, you'll be charged automatically!**

---

## 🔒 Security Best Practices

1. **Restrict SSH Access** (optional but recommended):
   - In Security Group, change SSH source from `0.0.0.0/0` to your IP only
   - Find your IP: https://www.whatsmyipaddress.com

2. **Enable AWS Budgets** (free, alerts you if costs exceed $1):
   - Go to AWS Console → Billing Dashboard → Budgets
   - Create a $1 budget alert

3. **Monitor Free Tier Usage**:
   - AWS Console → Billing Dashboard → Free Tier
   - Check current usage regularly

---

## 🛠️ Useful AWS Commands

### Check Instance Status

```bash
# View all instances
aws ec2 describe-instances --query 'Reservations[*].Instances[*].[InstanceId,PublicIpAddress,State.Name]' --region us-east-1

# View cost
# AWS Console → Billing Dashboard → Bills
```

### Stop Instance (if not in use - saves resource hours)

```
AWS Console → EC2 → Instances → Right-click instance → Instance State → Stop
```

### Restart Instance

```
AWS Console → EC2 → Instances → Right-click instance → Instance State → Start
```

### Terminate Instance (DELETES it)

```
AWS Console → EC2 → Instances → Right-click instance → Instance State → Terminate
# Only do this if you're done!
```

---

## 🆘 Troubleshooting

### Can't connect via SSH?

```bash
# Check security group allows port 22
# AWS Console → EC2 → Security Groups → docai-sg
# Should have inbound rule for SSH port 22

# Check key permissions
chmod 400 ~/Downloads/docai-key.pem

# Try connecting again
ssh -i ~/Downloads/docai-key.pem ubuntu@YOUR_PUBLIC_IP -v
# -v flag shows verbose output for debugging
```

### Instance won't start?

1. Wait 2-3 minutes after launching
2. Click refresh button in AWS Console
3. Check instance logs:
   - Right-click instance → Monitor and troubleshoot → View system log

### Out of free tier?

If you see charges starting:

1. Stop the instance immediately
2. Check AWS Console → Billing Dashboard
3. Contact AWS support to request credit

---

## 📊 Typical Costs (if outside free tier)

| Service             | Cost                   |
| ------------------- | ---------------------- |
| t2.micro EC2        | ~$9/month              |
| 30GB EBS Storage    | ~$3/month              |
| Data transfer       | Free (first 1GB/month) |
| **Estimated Total** | **~$12/month**         |

Still cheaper than most hosting!

---

## 🎯 Quick Checklist

- [ ] AWS account created
- [ ] EC2 instance launched (t2.micro, Ubuntu 22.04)
- [ ] Security group configured (ports 22, 80, 443, 3000, 8000)
- [ ] Key pair downloaded (`docai-key.pem`)
- [ ] SSH connection working
- [ ] Docker installation complete
- [ ] Application deployed
- [ ] Application accessible at `http://IP:3000`
- [ ] AWS Free Tier monitoring enabled

---

## 📞 Support

If you need help:

1. **AWS Support**: https://console.aws.amazon.com/support
2. **Check instance logs**: Right-click instance → Monitor → View system log
3. **Check Docker logs**: `docker-compose -f docker-compose.prod.yml logs`

---

## 🎉 You're Ready!

Your Document AI system is now running on a free AWS EC2 instance!

**Enjoy 12 months of free hosting** 🚀
