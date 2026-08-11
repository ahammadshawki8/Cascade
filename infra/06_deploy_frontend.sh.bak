#!/bin/bash
# Cascade — Frontend Deployment (AWS Amplify Hosting)
#
# Run AFTER 07_deploy_cloudfront.sh: the build bakes NEXT_PUBLIC_API_URL in at
# compile time, so the CloudFront URL has to exist before the build starts.
# Pointing this at the raw ALB produces a page that silently fails in the
# browser — https page, http API, mixed content blocked.
#
# Usage:
#   NEXT_PUBLIC_API_URL=https://dxxxx.cloudfront.net ./06_deploy_frontend.sh
#
# Optional:
#   GITHUB_REPO=https://github.com/<owner>/<repo>   connect a repo for CI builds
#   GITHUB_TOKEN=ghp_...                            required with GITHUB_REPO
#   BRANCH=main

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
PROJECT_NAME="cascade"
APP_NAME="${PROJECT_NAME}-frontend"
BRANCH="${BRANCH:-main}"

echo "=== Deploying Cascade frontend to Amplify ==="
echo ""

# ----------------------------------------------------------------------------
# Resolve the API URL
# ----------------------------------------------------------------------------

API_URL="${NEXT_PUBLIC_API_URL:-}"
if [[ -z "$API_URL" ]]; then
    DIST_DOMAIN=$(aws cloudfront list-distributions \
        --query "DistributionList.Items[?Comment=='${PROJECT_NAME}-api'].DomainName | [0]" \
        --output text 2>/dev/null || echo "None")
    if [[ "$DIST_DOMAIN" != "None" && -n "$DIST_DOMAIN" ]]; then
        API_URL="https://${DIST_DOMAIN}"
    fi
fi

if [[ -z "$API_URL" ]]; then
    echo "!! NEXT_PUBLIC_API_URL is not set and no CloudFront distribution was found."
    echo "   Run ./07_deploy_cloudfront.sh first, or pass the URL explicitly."
    exit 1
fi

if [[ "$API_URL" != https://* ]]; then
    echo "!! Refusing to build against a non-https API URL: $API_URL"
    echo "   Amplify serves over https; the browser would block every request"
    echo "   to an http origin as mixed content, including the SSE stream."
    exit 1
fi

echo "API URL: $API_URL"

ADMIN_TOKEN=$(aws secretsmanager get-secret-value \
    --secret-id "${PROJECT_NAME}/admin-token" \
    --region "$REGION" \
    --query SecretString --output text 2>/dev/null || echo "")
if [[ -z "$ADMIN_TOKEN" ]]; then
    echo "!! ${PROJECT_NAME}/admin-token not found — the Policy Panel and demo"
    echo "   reset will be unable to authenticate. Create it in 03_aws_bootstrap.sh."
fi

# The token is passed WITHOUT a NEXT_PUBLIC_ prefix on purpose.
#
# NEXT_PUBLIC_* is inlined into the client bundle at build time, so an earlier
# version of this script took the admin credential out of Secrets Manager and
# published it in the page source. It is now read server-side only, by the
# route handler at src/app/api/proxy/[...path]/route.ts.
#
# If you ever add it back with a NEXT_PUBLIC_ prefix, you are re-opening that
# hole.

# ----------------------------------------------------------------------------
# Create or reuse the Amplify app
# ----------------------------------------------------------------------------

APP_ID=$(aws amplify list-apps --region "$REGION" \
    --query "apps[?name=='${APP_NAME}'].appId | [0]" --output text 2>/dev/null || echo "None")

BUILD_SPEC=$(cat <<'YAML'
version: 1
frontend:
  phases:
    preBuild:
      commands:
        - npm ci
    build:
      commands:
        - npm run build
  artifacts:
    baseDirectory: .next
    files:
      - '**/*'
  cache:
    paths:
      - node_modules/**/*
      - .next/cache/**/*
YAML
)

if [[ "$APP_ID" == "None" || -z "$APP_ID" ]]; then
    echo "Creating Amplify app..."
    CREATE_ARGS=(
        --name "$APP_NAME"
        --platform WEB_COMPUTE          # Next.js SSR/app router, not static
        --region "$REGION"
        --build-spec "$BUILD_SPEC"
        --environment-variables "NEXT_PUBLIC_API_URL=${API_URL},CASCADE_API_URL=${API_URL},ADMIN_TOKEN=${ADMIN_TOKEN},AMPLIFY_MONOREPO_APP_ROOT=frontend"
    )
    if [[ -n "${GITHUB_REPO:-}" ]]; then
        if [[ -z "${GITHUB_TOKEN:-}" ]]; then
            echo "!! GITHUB_REPO set but GITHUB_TOKEN missing — cannot connect the repo."
            exit 1
        fi
        CREATE_ARGS+=(--repository "$GITHUB_REPO" --oauth-token "$GITHUB_TOKEN")
    fi

    APP_ID=$(aws amplify create-app "${CREATE_ARGS[@]}" --query 'app.appId' --output text)
    echo "✓ App created: $APP_ID"
else
    echo "Updating existing app $APP_ID..."
    aws amplify update-app \
        --app-id "$APP_ID" \
        --region "$REGION" \
        --build-spec "$BUILD_SPEC" \
        --environment-variables "NEXT_PUBLIC_API_URL=${API_URL},CASCADE_API_URL=${API_URL},ADMIN_TOKEN=${ADMIN_TOKEN},AMPLIFY_MONOREPO_APP_ROOT=frontend" \
        --no-cli-pager >/dev/null
    echo "✓ App updated"
fi

aws amplify create-branch \
    --app-id "$APP_ID" \
    --branch-name "$BRANCH" \
    --region "$REGION" \
    --no-cli-pager >/dev/null 2>&1 || echo "  (branch $BRANCH already exists)"

# ----------------------------------------------------------------------------
# Optional: gate the whole site behind basic auth
# ----------------------------------------------------------------------------
# The proxy stops the admin credential leaking, but it is not access control —
# without a login, anyone who can reach the site can still change policy or
# reset the demo. For a public judging link that is usually fine and even
# intended. When it isn't, this is the zero-code fix:
#
#   DEMO_USER=judge DEMO_PASSWORD=... ./06_deploy_frontend.sh
#
# Amplify enforces it at the edge, before any of our code runs.
if [[ -n "${DEMO_PASSWORD:-}" ]]; then
    DEMO_USER="${DEMO_USER:-judge}"
    CREDS=$(printf '%s:%s' "$DEMO_USER" "$DEMO_PASSWORD" | base64 | tr -d '\n')
    aws amplify update-branch \
        --app-id "$APP_ID" \
        --branch-name "$BRANCH" \
        --enable-basic-auth \
        --basic-auth-credentials "$CREDS" \
        --region "$REGION" \
        --no-cli-pager >/dev/null
    echo "✓ Basic auth enabled for branch $BRANCH (user: $DEMO_USER)"
else
    aws amplify update-branch \
        --app-id "$APP_ID" \
        --branch-name "$BRANCH" \
        --no-enable-basic-auth \
        --region "$REGION" \
        --no-cli-pager >/dev/null 2>&1 || true
    echo "  (site is publicly reachable — set DEMO_PASSWORD to gate it)"
fi

# ----------------------------------------------------------------------------
# Build
# ----------------------------------------------------------------------------

if [[ -n "${GITHUB_REPO:-}" ]]; then
    echo "Triggering a repository build..."
    JOB_ID=$(aws amplify start-job \
        --app-id "$APP_ID" \
        --branch-name "$BRANCH" \
        --job-type RELEASE \
        --region "$REGION" \
        --query 'jobSummary.jobId' --output text)
    echo "✓ Build started (job $JOB_ID)"
else
    # No repo connected — ship the working tree as a manual deployment so the
    # demo does not depend on GitHub being wired up.
    echo "No GITHUB_REPO set — performing a manual deployment of the local build..."
    cd "$(dirname "$0")/../frontend"

    NEXT_PUBLIC_API_URL="$API_URL" npm ci
    NEXT_PUBLIC_API_URL="$API_URL" CASCADE_API_URL="$API_URL" ADMIN_TOKEN="$ADMIN_TOKEN" npm run build

    ZIP_PATH="/tmp/${APP_NAME}.zip"
    rm -f "$ZIP_PATH"
    zip -qr "$ZIP_PATH" .next public package.json next.config.ts

    UPLOAD=$(aws amplify create-deployment \
        --app-id "$APP_ID" --branch-name "$BRANCH" --region "$REGION")
    JOB_ID=$(echo "$UPLOAD" | python -c 'import json,sys; print(json.load(sys.stdin)["jobId"])')
    UPLOAD_URL=$(echo "$UPLOAD" | python -c 'import json,sys; print(json.load(sys.stdin)["zipUploadUrl"])')

    curl -s -H "Content-Type: application/zip" --upload-file "$ZIP_PATH" "$UPLOAD_URL"
    aws amplify start-deployment \
        --app-id "$APP_ID" --branch-name "$BRANCH" --job-id "$JOB_ID" \
        --region "$REGION" --no-cli-pager >/dev/null

    cd "$(dirname "$0")"
    echo "✓ Manual deployment started (job $JOB_ID)"
fi

APP_URL="https://${BRANCH}.${APP_ID}.amplifyapp.com"

echo ""
echo "=== Frontend Deployment Started ==="
echo ""
echo "App ID:  $APP_ID"
echo "URL:     $APP_URL"
echo "API:     $API_URL"
echo ""
echo "Watch the build:"
echo "  aws amplify get-job --app-id $APP_ID --branch-name $BRANCH --job-id $JOB_ID --region $REGION"
echo ""
echo "Once it is live, confirm the browser can reach the API and the SSE stream:"
echo "  open $APP_URL   → the metric bar should populate and the LLM dot should be green"
