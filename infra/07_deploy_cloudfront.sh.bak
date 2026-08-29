#!/bin/bash
# Cascade — CloudFront Distribution
# Puts HTTPS in front of the ALB.
#
# Why this exists at all: Amplify serves the frontend over https, so a browser
# will refuse to call an http:// ALB from that page (mixed content) and will
# also refuse an EventSource to it. CloudFront terminates TLS and forwards to
# the ALB over http, so the frontend only ever talks to one https origin.
#
# Run this BEFORE 06_deploy_frontend.sh — Amplify needs the URL this prints.

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
PROJECT_NAME="cascade"
CALLER_REF="${PROJECT_NAME}-$(date +%s)"

echo "=== Creating CloudFront distribution for Cascade API ==="
echo ""

ALB_DNS=$(aws elbv2 describe-load-balancers \
    --names "${PROJECT_NAME}-alb" \
    --region "$REGION" \
    --query 'LoadBalancers[0].DNSName' --output text)

if [[ -z "$ALB_DNS" || "$ALB_DNS" == "None" ]]; then
    echo "!! No ALB named ${PROJECT_NAME}-alb. Run 04_deploy_ecs.sh first."
    exit 1
fi
echo "Origin: $ALB_DNS"

# Reuse the distribution if this script has already run.
EXISTING_ID=$(aws cloudfront list-distributions \
    --query "DistributionList.Items[?Comment=='${PROJECT_NAME}-api'].Id | [0]" \
    --output text 2>/dev/null || echo "None")

if [[ "$EXISTING_ID" != "None" && -n "$EXISTING_ID" ]]; then
    DIST_DOMAIN=$(aws cloudfront get-distribution --id "$EXISTING_ID" \
        --query 'Distribution.DomainName' --output text)
    echo "✓ Distribution already exists: $EXISTING_ID ($DIST_DOMAIN)"
else
    cat > /tmp/cf-config.json <<EOF
{
  "CallerReference": "${CALLER_REF}",
  "Comment": "${PROJECT_NAME}-api",
  "Enabled": true,
  "PriceClass": "PriceClass_100",
  "HttpVersion": "http2",
  "Origins": {
    "Quantity": 1,
    "Items": [
      {
        "Id": "alb-origin",
        "DomainName": "${ALB_DNS}",
        "CustomOriginConfig": {
          "HTTPPort": 80,
          "HTTPSPort": 443,
          "OriginProtocolPolicy": "http-only",
          "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
          "OriginReadTimeout": 60,
          "OriginKeepaliveTimeout": 60
        }
      }
    ]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "alb-origin",
    "ViewerProtocolPolicy": "redirect-to-https",
    "AllowedMethods": {
      "Quantity": 7,
      "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
      "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}
    },
    "Compress": false,
    "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
    "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3"
  },
  "CacheBehaviors": {
    "Quantity": 1,
    "Items": [
      {
        "PathPattern": "/api/*",
        "TargetOriginId": "alb-origin",
        "ViewerProtocolPolicy": "redirect-to-https",
        "AllowedMethods": {
          "Quantity": 7,
          "Items": ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"],
          "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}
        },
        "Compress": false,
        "CachePolicyId": "4135ea2d-6df8-44a3-9df3-4b5a84be39ad",
        "OriginRequestPolicyId": "216adef6-5c7f-47e4-b989-5492eafa07d3"
      }
    ]
  }
}
EOF

    # CachePolicyId       4135ea2d… = Managed-CachingDisabled
    # OriginRequestPolicy 216adef6… = Managed-AllViewer (forwards every header,
    #                                 cookie and query string to the origin)
    #
    # Caching MUST be disabled and compression MUST be off for /api/*:
    #   · SSE is a long-lived streaming response. CloudFront will buffer a
    #     compressed response and the dashboard receives nothing until the
    #     stream ends — which, for /api/events, is never.
    #   · Cached POSTs and metrics would make the demo show stale state.
    # The API also sends X-Accel-Buffering: no for the same reason.

    echo "Creating distribution (this takes a few minutes to propagate)..."
    DIST_JSON=$(aws cloudfront create-distribution --distribution-config file:///tmp/cf-config.json)
    EXISTING_ID=$(echo "$DIST_JSON" | python -c 'import json,sys; print(json.load(sys.stdin)["Distribution"]["Id"])')
    DIST_DOMAIN=$(echo "$DIST_JSON" | python -c 'import json,sys; print(json.load(sys.stdin)["Distribution"]["DomainName"])')
    echo "✓ Distribution created: $EXISTING_ID"
fi

echo ""
echo "Waiting for the distribution to finish deploying..."
aws cloudfront wait distribution-deployed --id "$EXISTING_ID" 2>/dev/null \
    || echo "  (still propagating — safe to continue, it will settle within ~15 min)"

echo ""
echo "=== CloudFront Ready ==="
echo ""
echo "Distribution ID: $EXISTING_ID"
echo "API base URL:    https://${DIST_DOMAIN}"
echo ""
echo "Verify:"
echo "  curl https://${DIST_DOMAIN}/health"
echo "  curl https://${DIST_DOMAIN}/api/metrics"
echo "  curl -N https://${DIST_DOMAIN}/api/events   # should stream, not buffer"
echo ""
echo "Next — deploy the frontend against this URL (never the raw ALB):"
echo "  NEXT_PUBLIC_API_URL=https://${DIST_DOMAIN} ./06_deploy_frontend.sh"
