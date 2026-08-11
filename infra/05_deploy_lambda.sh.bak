#!/bin/bash
# Cascade — Lambda Worker Deployment
# Outbox consumer: compile · rule_changed · relearn · recheck_suspect
#
# Two triggers:
#   SQS         cascade-events  — near-real-time, published post-commit (D5)
#   EventBridge every 60s       — sweeper for rows SQS never delivered
#
# The sweeper is what makes the outbox pattern correct rather than hopeful:
# if the post-commit publish fails, the work still happens within a minute.

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
PROJECT_NAME="cascade"
FUNCTION_NAME="${PROJECT_NAME}-worker"
QUEUE_NAME="${PROJECT_NAME}-events"
RUNTIME="python3.12"
BUILD_DIR="/tmp/${PROJECT_NAME}-lambda-build"
ZIP_PATH="/tmp/${FUNCTION_NAME}.zip"

echo "=== Deploying Cascade worker to Lambda ==="
echo "Region:   $REGION"
echo "Account:  $ACCOUNT_ID"
echo "Function: $FUNCTION_NAME"
echo ""

# ============================================================================
# Package
# ============================================================================

echo "Packaging worker..."
rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$BUILD_DIR"

cd "$(dirname "$0")/../backend"

# The worker imports app.core.* (compiler, executor, freshness) and app.db,
# so the whole app package ships with it — the engine is shared, not duplicated.
cp -r app worker "$BUILD_DIR/"

# Build for Lambda's platform, not the machine running this script. Without
# these flags pip resolves macOS/Windows wheels for psycopg's binary extension
# and the function fails at import time with a cryptic ELF error.
python -m pip install \
    --target "$BUILD_DIR" \
    --platform manylinux2014_x86_64 \
    --implementation cp \
    --python-version 3.12 \
    --only-binary=:all: \
    --upgrade \
    "psycopg[binary,pool]>=3.1" \
    "pydantic>=2.6" \
    "pydantic-settings>=2.2" \
    "httpx>=0.27" \
    --quiet

# boto3 is already present in the Lambda runtime; shipping it just inflates
# the package and risks shadowing the runtime's newer version.

find "$BUILD_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -type d -name "tests" -prune -exec rm -rf {} + 2>/dev/null || true

(cd "$BUILD_DIR" && zip -qr "$ZIP_PATH" .)
echo "✓ Package built: $(du -h "$ZIP_PATH" | cut -f1)"

cd "$(dirname "$0")"

# ============================================================================
# Resolve dependencies created by 03_aws_bootstrap.sh
# ============================================================================

ROLE_ARN="arn:aws:iam::${ACCOUNT_ID}:role/${PROJECT_NAME}-lambda-role"
QUEUE_URL=$(aws sqs get-queue-url --queue-name "$QUEUE_NAME" --region "$REGION" --query QueueUrl --output text)
QUEUE_ARN=$(aws sqs get-queue-attributes \
    --queue-url "$QUEUE_URL" \
    --attribute-names QueueArn \
    --region "$REGION" \
    --query 'Attributes.QueueArn' --output text)

DSN_WORKER_ARN=$(aws secretsmanager describe-secret \
    --secret-id "${PROJECT_NAME}/dsn-worker" --region "$REGION" --query ARN --output text)

# The worker POSTs SSE events back to the API, so it needs the API's address
# and the shared internal secret. Falls back to the ALB if CloudFront is not up.
API_BASE_URL="${API_BASE_URL:-}"
if [[ -z "$API_BASE_URL" ]]; then
    ALB_DNS=$(aws elbv2 describe-load-balancers \
        --names "${PROJECT_NAME}-alb" \
        --region "$REGION" \
        --query 'LoadBalancers[0].DNSName' --output text 2>/dev/null || echo "")
    [[ -n "$ALB_DNS" ]] && API_BASE_URL="http://${ALB_DNS}"
fi
if [[ -z "$API_BASE_URL" ]]; then
    echo "!! API_BASE_URL not set and no ALB found — run 04_deploy_ecs.sh first," \
         "or export API_BASE_URL. SSE notifications will be skipped until then."
fi

# Lambda has no native Secrets Manager integration the way an ECS task
# definition does, so the DSN is resolved once here at deploy time. Lambda
# encrypts environment variables at rest with KMS; the value never lands in
# git or in a build artifact.
DATABASE_URL=$(aws secretsmanager get-secret-value \
    --secret-id "${PROJECT_NAME}/dsn-worker" \
    --region "$REGION" \
    --query SecretString --output text)
INTERNAL_SSE_SECRET=$(aws secretsmanager get-secret-value \
    --secret-id "${PROJECT_NAME}/internal-sse" \
    --region "$REGION" \
    --query SecretString --output text)

# AWS_REGION is reserved — Lambda sets it for us and rejects it here.
ENV_VARS="{
    CASCADE_STUB_MODE=false,
    RUN_WORKER_IN_PROCESS=false,
    DATABASE_URL=${DATABASE_URL},
    INTERNAL_SSE_SECRET=${INTERNAL_SSE_SECRET},
    BEDROCK_AGENT_MODEL_ID=anthropic.claude-sonnet-5,
    BEDROCK_FAST_MODEL_ID=anthropic.claude-haiku-4-5,
    BEDROCK_EMBED_MODEL_ID=amazon.titan-embed-text-v2:0,
    EPISODES_BUCKET=${PROJECT_NAME}-episodes-${ACCOUNT_ID},
    CASCADE_QUEUE_URL=${QUEUE_URL},
    API_BASE_URL=${API_BASE_URL}
}"
ENV_VARS=$(echo "$ENV_VARS" | tr -d ' \n')

# ============================================================================
# Create or update the function
# ============================================================================

if aws lambda get-function --function-name "$FUNCTION_NAME" --region "$REGION" >/dev/null 2>&1; then
    echo "Updating existing function..."
    aws lambda update-function-code \
        --function-name "$FUNCTION_NAME" \
        --zip-file "fileb://${ZIP_PATH}" \
        --region "$REGION" \
        --no-cli-pager >/dev/null

    aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"

    aws lambda update-function-configuration \
        --function-name "$FUNCTION_NAME" \
        --handler worker.handler.lambda_handler \
        --timeout 120 \
        --memory-size 1024 \
        --environment "Variables=${ENV_VARS}" \
        --region "$REGION" \
        --no-cli-pager >/dev/null
else
    echo "Creating function..."
    aws lambda create-function \
        --function-name "$FUNCTION_NAME" \
        --runtime "$RUNTIME" \
        --role "$ROLE_ARN" \
        --handler worker.handler.lambda_handler \
        --zip-file "fileb://${ZIP_PATH}" \
        --timeout 120 \
        --memory-size 1024 \
        --environment "Variables=${ENV_VARS}" \
        --region "$REGION" \
        --no-cli-pager >/dev/null
fi

aws lambda wait function-updated --function-name "$FUNCTION_NAME" --region "$REGION"

FUNCTION_ARN=$(aws lambda get-function --function-name "$FUNCTION_NAME" \
    --region "$REGION" --query 'Configuration.FunctionArn' --output text)
echo "✓ Function deployed: $FUNCTION_ARN"
echo "  DSN sourced from ${PROJECT_NAME}/dsn-worker ($DSN_WORKER_ARN)"

# ============================================================================
# SQS trigger
# ============================================================================

echo "Wiring SQS trigger..."
EXISTING_MAPPING=$(aws lambda list-event-source-mappings \
    --function-name "$FUNCTION_NAME" \
    --event-source-arn "$QUEUE_ARN" \
    --region "$REGION" \
    --query 'EventSourceMappings[0].UUID' --output text 2>/dev/null || echo "None")

if [[ "$EXISTING_MAPPING" == "None" || -z "$EXISTING_MAPPING" ]]; then
    aws lambda create-event-source-mapping \
        --function-name "$FUNCTION_NAME" \
        --event-source-arn "$QUEUE_ARN" \
        --batch-size 10 \
        --maximum-batching-window-in-seconds 5 \
        --function-response-types ReportBatchItemFailures \
        --region "$REGION" \
        --no-cli-pager >/dev/null
    echo "✓ SQS trigger created (partial batch failure reporting enabled)"
else
    echo "✓ SQS trigger already present ($EXISTING_MAPPING)"
fi

# ============================================================================
# EventBridge sweeper (every 60s, D5)
# ============================================================================

echo "Wiring EventBridge sweeper..."
RULE_NAME="${PROJECT_NAME}-sweeper"

aws events put-rule \
    --name "$RULE_NAME" \
    --schedule-expression "rate(1 minute)" \
    --description "Cascade outbox sweeper — claims rows SQS did not deliver" \
    --region "$REGION" \
    --no-cli-pager >/dev/null

aws lambda add-permission \
    --function-name "$FUNCTION_NAME" \
    --statement-id "${RULE_NAME}-invoke" \
    --action lambda:InvokeFunction \
    --principal events.amazonaws.com \
    --source-arn "arn:aws:events:${REGION}:${ACCOUNT_ID}:rule/${RULE_NAME}" \
    --region "$REGION" \
    --no-cli-pager >/dev/null 2>&1 || echo "  (permission already granted)"

# handler.lambda_handler routes on source == aws.events
aws events put-targets \
    --rule "$RULE_NAME" \
    --targets "Id=1,Arn=${FUNCTION_ARN},Input={\"source\":\"aws.events\",\"sweeper\":true}" \
    --region "$REGION" \
    --no-cli-pager >/dev/null

echo "✓ Sweeper scheduled every 60s"

# ============================================================================
# Summary
# ============================================================================

echo ""
echo "=== Lambda Deployment Complete ==="
echo ""
echo "Function: $FUNCTION_NAME"
echo "Queue:    $QUEUE_URL"
echo "Sweeper:  $RULE_NAME (rate(1 minute))"
echo ""
echo "Verify:"
echo "  aws logs tail /aws/lambda/${FUNCTION_NAME} --follow --region $REGION"
echo ""
echo "Force one sweep now:"
echo "  aws lambda invoke --function-name $FUNCTION_NAME \\"
echo "    --payload '{\"source\":\"aws.events\"}' --cli-binary-format raw-in-base64-out \\"
echo "    --region $REGION /dev/stdout"
echo ""
echo "Next: ./07_deploy_cloudfront.sh, then ./06_deploy_frontend.sh"
