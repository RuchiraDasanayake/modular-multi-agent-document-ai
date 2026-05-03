#!/bin/bash
# AWS EC2 Instance Quick Launcher
# This creates the EC2 instance via AWS CLI
# Prerequisites: AWS CLI installed and configured

set -e

echo "================================================================"
echo "  AWS Free Tier EC2 Instance Launcher"
echo "================================================================"
echo ""

# Check AWS CLI installed
if ! command -v aws &> /dev/null; then
    echo "[ERROR] AWS CLI not installed"
    echo "        Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    exit 1
fi

# Check AWS configured
if ! aws sts get-caller-identity > /dev/null 2>&1; then
    echo "[ERROR] AWS CLI not configured"
    echo "        Run: aws configure"
    echo "        Then provide your AWS Access Key ID and Secret Access Key"
    exit 1
fi

echo "[OK] AWS CLI configured"
echo ""

# Get parameters
read -p "Instance name (default: DocumentAI): " INSTANCE_NAME
INSTANCE_NAME=${INSTANCE_NAME:-DocumentAI}

read -p "Key pair name (default: docai-key): " KEY_NAME
KEY_NAME=${KEY_NAME:-docai-key}

read -p "AWS Region (default: us-east-1): " REGION
REGION=${REGION:-us-east-1}

echo ""
echo "Creating instance..."
echo "  Name: $INSTANCE_NAME"
echo "  Key pair: $KEY_NAME"
echo "  Region: $REGION"
echo "  Type: t2.micro (free tier)"
echo "  OS: Ubuntu 22.04 LTS"
echo "  Storage: 30GB"
echo ""

# Create key pair if not exists
if ! aws ec2 describe-key-pairs --key-names "$KEY_NAME" --region "$REGION" > /dev/null 2>&1; then
    echo "[*] Creating key pair: $KEY_NAME"
    aws ec2 create-key-pair --key-name "$KEY_NAME" --region "$REGION" --query 'KeyMaterial' --output text > "$KEY_NAME.pem"
    chmod 400 "$KEY_NAME.pem"
    echo "[OK] Key pair created: $KEY_NAME.pem"
else
    echo "[OK] Key pair already exists: $KEY_NAME"
fi

echo ""
echo "[*] Creating security group..."

# Create security group
SG_NAME="docai-sg"
SG_ID=$(aws ec2 create-security-group \
    --group-name "$SG_NAME" \
    --description "Security group for Document AI" \
    --region "$REGION" \
    --query 'GroupId' \
    --output text 2>/dev/null || echo "")

if [ -z "$SG_ID" ]; then
    # Group might already exist
    SG_ID=$(aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=$SG_NAME" \
        --region "$REGION" \
        --query 'SecurityGroups[0].GroupId' \
        --output text)
fi

echo "[OK] Security group: $SG_ID"

# Add inbound rules
echo "[*] Configuring security group rules..."

for PORT in 22 80 443 3000 8000; do
    aws ec2 authorize-security-group-ingress \
        --group-id "$SG_ID" \
        --protocol tcp \
        --port "$PORT" \
        --cidr 0.0.0.0/0 \
        --region "$REGION" 2>/dev/null || true
done

echo "[OK] Security group configured"
echo ""

# Get Ubuntu 22.04 LTS AMI
echo "[*] Finding Ubuntu 22.04 LTS AMI..."
AMI_ID=$(aws ec2 describe-images \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
    --output text \
    --region "$REGION")

echo "[OK] AMI: $AMI_ID"
echo ""

# Launch instance
echo "[*] Launching EC2 instance..."
INSTANCE_ID=$(aws ec2 run-instances \
    --image-id "$AMI_ID" \
    --instance-type t2.micro \
    --key-name "$KEY_NAME" \
    --security-group-ids "$SG_ID" \
    --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp2,DeleteOnTermination=true}" \
    --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$INSTANCE_NAME}]" \
    --region "$REGION" \
    --query 'Instances[0].InstanceId' \
    --output text)

echo "[OK] Instance launched: $INSTANCE_ID"
echo ""

# Wait for instance to get public IP
echo "[*] Waiting for instance to start (this may take 30 seconds)..."
sleep 30

PUBLIC_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

echo ""
echo "================================================================"
echo "  EC2 Instance Created Successfully!"
echo "================================================================"
echo ""
echo "Instance Details:"
echo "  Instance ID: $INSTANCE_ID"
echo "  Instance Name: $INSTANCE_NAME"
echo "  Public IP: $PUBLIC_IP"
echo "  Region: $REGION"
echo "  Key pair: $KEY_NAME.pem"
echo ""
echo "SSH Command:"
echo "  ssh -i $KEY_NAME.pem ubuntu@$PUBLIC_IP"
echo ""
echo "Next Steps:"
echo "  1. Save your key pair file safely: $KEY_NAME.pem"
echo "  2. Connect via SSH using the command above"
echo "  3. Follow docs/AWS_FREE_TIER_SETUP.md step 5 to deploy"
echo ""
echo "Quick Deploy:"
echo "  ssh -i $KEY_NAME.pem ubuntu@$PUBLIC_IP"
echo "  curl -O https://raw.githubusercontent.com/YOUR_ORG/modular-multi-agent-document-ai/feature/IDPO/scripts/vps-setup.sh"
echo "  sudo bash vps-setup.sh"
echo ""
