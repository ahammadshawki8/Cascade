#!/bin/bash
# Cascade — ECS (Fargate) Deployment
# Deploys FastAPI backend with executor

set -euo pipefail

mkdir -p .awstmp

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
PROJECT_NAME="cascade"
CLUSTER_NAME="${PROJECT_NAME}-cluster"
SERVICE_NAME="${PROJECT_NAME}-api"
TASK_FAMILY="${PROJECT_NAME}-api"

echo "=== Deploying Cascade API to ECS Fargate ==="
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo ""

# ============================================================================
# Build and push Docker image
# ============================================================================

ECR_URI="${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com/${PROJECT_NAME}-api"
IMAGE_TAG="latest"

echo "Building Docker image..."
cd ../backend

# Fargate rejects arm64 — force amd64
docker build --platform linux/amd64 -t "${PROJECT_NAME}-api:${IMAGE_TAG}" .

echo "Pushing to ECR..."
aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_URI"
docker tag "${PROJECT_NAME}-api:${IMAGE_TAG}" "$ECR_URI:${IMAGE_TAG}"
docker push "$ECR_URI:${IMAGE_TAG}"

echo "✓ Image pushed: $ECR_URI:$IMAGE_TAG"
cd ../infra

# ============================================================================
# Create ECS cluster
# ============================================================================

echo "Creating ECS cluster..."
aws ecs create-cluster \
    --cluster-name "$CLUSTER_NAME" \
    --region "$REGION" \
    2>/dev/null || echo "Cluster already exists"

# ============================================================================
# Create CloudWatch log group
# ============================================================================

LOG_GROUP="/ecs/${PROJECT_NAME}"
aws logs create-log-group --log-group-name "$LOG_GROUP" 2>/dev/null || echo "Log group exists"
aws logs put-retention-policy --log-group-name "$LOG_GROUP" --retention-in-days 7

# ============================================================================
# Create task definition
# ============================================================================

echo "Registering task definition..."

# Get secret ARNs
DSN_APP_ARN=$(aws secretsmanager describe-secret --secret-id "${PROJECT_NAME}/dsn-app" --query ARN --output text)
INTERNAL_SECRET_ARN=$(aws secretsmanager describe-secret --secret-id "${PROJECT_NAME}/internal-sse" --query ARN --output text)
# Without this the container falls back to config.py's default admin token,
# leaving every mutating endpoint on a value published in the repo.
ADMIN_TOKEN_ARN=$(aws secretsmanager describe-secret --secret-id "${PROJECT_NAME}/admin-token" --query ARN --output text)

cat > .awstmp/task-def.json <<EOF
{
  "family": "$TASK_FAMILY",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT_NAME}-ecs-execution-role",
  "taskRoleArn": "arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT_NAME}-ecs-task-role",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "$ECR_URI:$IMAGE_TAG",
      "essential": true,
      "portMappings": [
        {
          "containerPort": 8000,
          "protocol": "tcp"
        }
      ],
      "environment": [
        {"name": "AWS_REGION", "value": "$REGION"},
        {"name": "CASCADE_STUB_MODE", "value": "false"},
        {"name": "BEDROCK_AGENT_MODEL_ID", "value": "us.anthropic.claude-sonnet-4-6"},
        {"name": "BEDROCK_FAST_MODEL_ID", "value": "us.anthropic.claude-haiku-4-5-20251001-v1:0"},
        {"name": "BEDROCK_EMBED_MODEL_ID", "value": "amazon.titan-embed-text-v2:0"},
        {"name": "EPISODES_BUCKET", "value": "${PROJECT_NAME}-episodes-${ACCOUNT_ID}"},
        {"name": "CASCADE_QUEUE_URL", "value": "https://sqs.${REGION}.amazonaws.com/${ACCOUNT_ID}/${PROJECT_NAME}-events"},
        {"name": "ENABLE_SNS_FANOUT", "value": "false"}
      ],
      "secrets": [
        {"name": "DATABASE_URL", "valueFrom": "$DSN_APP_ARN"},
        {"name": "INTERNAL_SSE_SECRET", "valueFrom": "$INTERNAL_SECRET_ARN"},
        {"name": "ADMIN_TOKEN", "valueFrom": "$ADMIN_TOKEN_ARN"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "$LOG_GROUP",
          "awslogs-region": "$REGION",
          "awslogs-stream-prefix": "api"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 60
      }
    }
  ]
}
EOF

TASK_DEF_ARN=$(aws ecs register-task-definition \
    --cli-input-json file://.awstmp/task-def.json \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

echo "✓ Task definition registered: $TASK_DEF_ARN"

# ============================================================================
# Create Application Load Balancer
# ============================================================================

echo "Creating Application Load Balancer..."

# Get default VPC
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text)
SUBNETS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[*].SubnetId' --output text)
SUBNET_1=$(echo $SUBNETS | awk '{print $1}')
SUBNET_2=$(echo $SUBNETS | awk '{print $2}')

# Create security group for ALB
ALB_SG_ID=$(aws ec2 create-security-group \
    --group-name "${PROJECT_NAME}-alb-sg" \
    --description "Security group for Cascade ALB" \
    --vpc-id "$VPC_ID" \
    --query 'GroupId' \
    --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=${PROJECT_NAME}-alb-sg" \
        --query 'SecurityGroups[0].GroupId' \
        --output text)

# Allow HTTP from anywhere (CloudFront will front this)
aws ec2 authorize-security-group-ingress \
    --group-id "$ALB_SG_ID" \
    --protocol tcp \
    --port 80 \
    --cidr 0.0.0.0/0 \
    2>/dev/null || echo "Ingress rule exists"

# Create security group for ECS tasks
ECS_SG_ID=$(aws ec2 create-security-group \
    --group-name "${PROJECT_NAME}-ecs-sg" \
    --description "Security group for Cascade ECS tasks" \
    --vpc-id "$VPC_ID" \
    --query 'GroupId' \
    --output text 2>/dev/null || \
    aws ec2 describe-security-groups \
        --filters "Name=group-name,Values=${PROJECT_NAME}-ecs-sg" \
        --query 'SecurityGroups[0].GroupId' \
        --output text)

# Allow traffic from ALB only
aws ec2 authorize-security-group-ingress \
    --group-id "$ECS_SG_ID" \
    --protocol tcp \
    --port 8000 \
    --source-group "$ALB_SG_ID" \
    2>/dev/null || echo "Ingress rule exists"

# Create ALB
ALB_ARN=$(aws elbv2 create-load-balancer \
    --name "${PROJECT_NAME}-alb" \
    --subnets "$SUBNET_1" "$SUBNET_2" \
    --security-groups "$ALB_SG_ID" \
    --scheme internet-facing \
    --type application \
    --ip-address-type ipv4 \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text 2>/dev/null || \
    aws elbv2 describe-load-balancers \
        --names "${PROJECT_NAME}-alb" \
        --query 'LoadBalancers[0].LoadBalancerArn' \
        --output text)

ALB_DNS=$(aws elbv2 describe-load-balancers \
    --load-balancer-arns "$ALB_ARN" \
    --query 'LoadBalancers[0].DNSName' \
    --output text)

echo "✓ ALB created: $ALB_DNS"

# Create target group
TG_ARN=$(aws elbv2 create-target-group \
    --name "${PROJECT_NAME}-tg" \
    --protocol HTTP \
    --port 8000 \
    --vpc-id "$VPC_ID" \
    --target-type ip \
    --health-check-path /health \
    --health-check-interval-seconds 30 \
    --health-check-timeout-seconds 5 \
    --healthy-threshold-count 2 \
    --unhealthy-threshold-count 3 \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text 2>/dev/null || \
    aws elbv2 describe-target-groups \
        --names "${PROJECT_NAME}-tg" \
        --query 'TargetGroups[0].TargetGroupArn' \
        --output text)

# Create listener
aws elbv2 create-listener \
    --load-balancer-arn "$ALB_ARN" \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn="$TG_ARN" \
    2>/dev/null || echo "Listener exists"

# ============================================================================
# Create ECS service
# ============================================================================

echo "Creating ECS service..."

aws ecs create-service \
    --cluster "$CLUSTER_NAME" \
    --service-name "$SERVICE_NAME" \
    --task-definition "$TASK_DEF_ARN" \
    --desired-count 1 \
    --launch-type FARGATE \
    --network-configuration "awsvpcConfiguration={subnets=[$SUBNET_1,$SUBNET_2],securityGroups=[$ECS_SG_ID],assignPublicIp=ENABLED}" \
    --load-balancers "targetGroupArn=$TG_ARN,containerName=api,containerPort=8000" \
    --health-check-grace-period-seconds 60 \
    2>/dev/null || echo "Service already exists, updating..."

# Update if exists
aws ecs update-service \
    --cluster "$CLUSTER_NAME" \
    --service "$SERVICE_NAME" \
    --task-definition "$TASK_DEF_ARN" \
    --force-new-deployment \
    2>/dev/null || true

echo "✓ ECS service deployed"

# ============================================================================
# Summary
# ============================================================================

echo ""
echo "=== ECS Deployment Complete ==="
echo ""
echo "Service: $SERVICE_NAME"
echo "Cluster: $CLUSTER_NAME"
echo "ALB DNS: $ALB_DNS"
echo ""
echo "Test the API:"
echo "  curl http://$ALB_DNS/health"
echo "  curl http://$ALB_DNS/api/metrics"
echo ""
echo "Next steps:"
echo "1. Create CloudFront distribution pointing to this ALB (see 07_deploy_cloudfront.sh)"
echo "2. Deploy Lambda worker (see 05_deploy_lambda.sh)"
echo "3. Deploy frontend to Amplify with CloudFront URL (see 06_deploy_frontend.sh)"
