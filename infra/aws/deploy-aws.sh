#!/usr/bin/env bash
#
# deploy-aws.sh — Deploy MyChatbot to AWS App Runner (macOS)
#
# Usage:
#   chmod +x infra/aws/deploy-aws.sh
#   ./infra/aws/deploy-aws.sh
#
set -euo pipefail

# ── Configuration (edit these) ───────────────────────────────────────────────
AWS_REGION="${AWS_REGION:-us-east-1}"
AWS_ACCOUNT_ID="${AWS_ACCOUNT_ID:-}"
SERVICE_NAME="mychatbot"
ECR_REPO="mychatbot"

DB_PASSWORD="${DB_PASSWORD:-$(openssl rand -base64 16)}"

OPENAI_API_KEY="${OPENAI_API_KEY:-}"
CHROMA_API_KEY="${CHROMA_API_KEY:-}"
CHROMA_TENANT="696cf798-1423-4a5f-bb61-c055be3b6318"
CHROMA_DATABASE="chatbotqa"

# ── Colors ───────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; exit 1; }

# ── Pre-flight checks ───────────────────────────────────────────────────────
[[ -z "$OPENAI_API_KEY" ]] && error "Set OPENAI_API_KEY env var"
[[ -z "$CHROMA_API_KEY" ]] && error "Set CHROMA_API_KEY env var"

# ── Step 1: Install prerequisites ────────────────────────────────────────────
info "Step 1/9: Checking prerequisites..."

if ! command -v brew &>/dev/null; then
  warn "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
fi

if ! command -v aws &>/dev/null; then
  warn "Installing AWS CLI..."
  brew install awscli
fi

if ! command -v docker &>/dev/null; then
  warn "Installing Docker..."
  brew install --cask docker
  echo "Please start Docker Desktop, then re-run this script."
  exit 1
fi

# ── Step 2: Authenticate ────────────────────────────────────────────────────
info "Step 2/9: Checking AWS credentials..."
if ! aws sts get-caller-identity &>/dev/null; then
  warn "Not authenticated. Running 'aws configure'..."
  aws configure
fi

if [[ -z "$AWS_ACCOUNT_ID" ]]; then
  AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
fi
info "  Account: $AWS_ACCOUNT_ID"

ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}"

# ── Step 3: Create ECR repository ───────────────────────────────────────────
info "Step 3/9: Creating ECR repository..."
aws ecr describe-repositories --repository-names "$ECR_REPO" --region "$AWS_REGION" &>/dev/null || \
  aws ecr create-repository --repository-name "$ECR_REPO" --region "$AWS_REGION" --image-scanning-configuration scanOnPush=true

# ── Step 4: Build Docker image ───────────────────────────────────────────────
info "Step 4/9: Building Docker image..."
docker build -t "${ECR_REPO}:latest" .

# ── Step 5: Push to ECR ─────────────────────────────────────────────────────
info "Step 5/9: Pushing image to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
docker tag "${ECR_REPO}:latest" "${ECR_URI}:latest"
docker push "${ECR_URI}:latest"

# ── Step 6: Create RDS PostgreSQL ────────────────────────────────────────────
info "Step 6/9: Creating RDS PostgreSQL instance..."

# Create default VPC subnets if needed
DEFAULT_VPC=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region "$AWS_REGION")
if [[ "$DEFAULT_VPC" == "None" ]]; then
  aws ec2 create-default-vpc --region "$AWS_REGION" || true
  DEFAULT_VPC=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text --region "$AWS_REGION")
fi

# Security group for RDS
SG_ID=$(aws ec2 describe-security-groups --filters "Name=group-name,Values=mychatbot-db-sg" "Name=vpc-id,Values=$DEFAULT_VPC" --query "SecurityGroups[0].GroupId" --output text --region "$AWS_REGION" 2>/dev/null || echo "None")
if [[ "$SG_ID" == "None" ]]; then
  SG_ID=$(aws ec2 create-security-group --group-name mychatbot-db-sg --description "MyChatbot DB" --vpc-id "$DEFAULT_VPC" --region "$AWS_REGION" --query "GroupId" --output text)
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp --port 5432 --cidr 0.0.0.0/0 --region "$AWS_REGION"
fi

# Create RDS instance
if ! aws rds describe-db-instances --db-instance-identifier mychatbot-db --region "$AWS_REGION" &>/dev/null; then
  aws rds create-db-instance \
    --db-instance-identifier mychatbot-db \
    --db-instance-class db.t4g.micro \
    --engine postgres \
    --engine-version 16 \
    --master-username mychatbot \
    --master-user-password "$DB_PASSWORD" \
    --db-name mychatbot \
    --allocated-storage 20 \
    --storage-type gp3 \
    --vpc-security-group-ids "$SG_ID" \
    --publicly-accessible \
    --backup-retention-period 7 \
    --region "$AWS_REGION"

  info "  Waiting for RDS to be available (this takes ~5 min)..."
  aws rds wait db-instance-available --db-instance-identifier mychatbot-db --region "$AWS_REGION"
fi

DB_HOST=$(aws rds describe-db-instances --db-instance-identifier mychatbot-db --region "$AWS_REGION" --query "DBInstances[0].Endpoint.Address" --output text)
DB_PORT=$(aws rds describe-db-instances --db-instance-identifier mychatbot-db --region "$AWS_REGION" --query "DBInstances[0].Endpoint.Port" --output text)
DATABASE_URL="postgres://mychatbot:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/mychatbot"
info "  Database: $DB_HOST:$DB_PORT"

# ── Step 7: Initialize DB schema ────────────────────────────────────────────
info "Step 7/9: Initializing database schema..."
if command -v psql &>/dev/null; then
  PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U mychatbot -d mychatbot -f backend/sql/schema.sql && info "  Schema applied." || warn "  Schema may already exist."
else
  warn "  psql not found. Install with: brew install libpq"
  warn "  Then run: PGPASSWORD='$DB_PASSWORD' psql -h $DB_HOST -U mychatbot -d mychatbot -f backend/sql/schema.sql"
fi

# ── Step 8: Deploy App Runner ───────────────────────────────────────────────
info "Step 8/9: Deploying to App Runner..."

# Create App Runner access role for ECR
ROLE_NAME="mychatbot-apprunner-ecr-role"
if ! aws iam get-role --role-name "$ROLE_NAME" &>/dev/null; then
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document '{
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "build.apprunner.amazonaws.com"},
        "Action": "sts:AssumeRole"
      }]
    }'
  aws iam attach-role-policy \
    --role-name "$ROLE_NAME" \
    --policy-arn arn:aws:iam::policy/service-role/AWSAppRunnerServicePolicyForECRAccess
  info "  Waiting for IAM role propagation..."
  sleep 15
fi
ACCESS_ROLE_ARN=$(aws iam get-role --role-name "$ROLE_NAME" --query "Role.Arn" --output text)

# Check if service exists
EXISTING_SERVICE=$(aws apprunner list-services --region "$AWS_REGION" --query "ServiceSummaryList[?ServiceName=='$SERVICE_NAME'].ServiceArn" --output text 2>/dev/null || echo "")

if [[ -z "$EXISTING_SERVICE" ]]; then
  aws apprunner create-service \
    --service-name "$SERVICE_NAME" \
    --region "$AWS_REGION" \
    --source-configuration "{
      \"AuthenticationConfiguration\": {\"AccessRoleArn\": \"$ACCESS_ROLE_ARN\"},
      \"ImageRepository\": {
        \"ImageIdentifier\": \"${ECR_URI}:latest\",
        \"ImageRepositoryType\": \"ECR\",
        \"ImageConfiguration\": {
          \"Port\": \"8080\",
          \"RuntimeEnvironmentVariables\": {
            \"NODE_ENV\": \"production\",
            \"PORT\": \"8080\",
            \"DATABASE_URL\": \"${DATABASE_URL}\",
            \"CHROMA_MODE\": \"cloud\",
            \"CHROMA_API_KEY\": \"${CHROMA_API_KEY}\",
            \"CHROMA_TENANT\": \"${CHROMA_TENANT}\",
            \"CHROMA_DATABASE\": \"${CHROMA_DATABASE}\",
            \"OPENAI_API_KEY\": \"${OPENAI_API_KEY}\",
            \"STORAGE_PROVIDER\": \"disk\",
            \"FRONTEND_DIST_PATH\": \"/app/frontend/dist\",
            \"PYTHON_BIN\": \"/app/python/.venv/bin/python3\",
            \"PYTHON_PROJECT_ROOT\": \"/app/python\"
          }
        }
      }
    }" \
    --instance-configuration "{\"Cpu\":\"1 vCPU\",\"Memory\":\"2 GB\"}" \
    --health-check-configuration "{\"Protocol\":\"HTTP\",\"Path\":\"/api/health\",\"Interval\":10,\"Timeout\":5,\"HealthyThreshold\":1,\"UnhealthyThreshold\":5}"

  info "  Service created. Waiting for deployment (2-5 min)..."
else
  warn "  Service already exists. Triggering redeployment..."
  aws apprunner start-deployment --service-arn "$EXISTING_SERVICE" --region "$AWS_REGION"
fi

# ── Step 9: Get URL ─────────────────────────────────────────────────────────
info "Step 9/9: Getting service URL..."
sleep 10
SERVICE_URL=$(aws apprunner list-services --region "$AWS_REGION" --query "ServiceSummaryList[?ServiceName=='$SERVICE_NAME'].ServiceUrl" --output text)

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "  ${GREEN}Deployed!${NC}  https://${SERVICE_URL}"
echo ""
echo "  Your conversations are at:"
echo "    https://${SERVICE_URL}/c/<conversation-id>"
echo ""
echo "  DB password: $DB_PASSWORD  (save this!)"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Next: map your domain chatbotqa.app"
echo "  1. In AWS App Runner console → Custom domains → Link domain → chatbotqa.app"
echo "  2. Add the CNAME/A records shown to GoDaddy DNS settings."
