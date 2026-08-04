#!/bin/bash
# Cascade — CockroachDB Cloud Cluster Provisioning
# Day 0 Contract Step 1

set -euo pipefail

CLUSTER_NAME="cascade-demo"
REGION="us-east-1"
CLOUD_PROVIDER="aws"

echo "=== Provisioning CockroachDB Cloud Cluster ==="
echo "Cluster: $CLUSTER_NAME"
echo "Region: $REGION"
echo "Provider: $CLOUD_PROVIDER"
echo ""

# Check if ccloud is installed
if ! command -v ccloud &> /dev/null; then
    echo "ERROR: ccloud CLI not found. Install from https://www.cockroachlabs.com/docs/cockroachcloud/ccloud-get-started.html"
    exit 1
fi

# Check if authenticated
if ! ccloud auth whoami &> /dev/null; then
    echo "ERROR: Not authenticated. Run: ccloud auth login"
    exit 1
fi

# Create cluster (free tier)
echo "Creating cluster..."
CLUSTER_ID=$(ccloud cluster create "$CLUSTER_NAME" \
    --cloud "$CLOUD_PROVIDER" \
    --region "$REGION" \
    --plan serverless \
    --output json | jq -r '.id')

if [ -z "$CLUSTER_ID" ]; then
    echo "ERROR: Failed to create cluster"
    exit 1
fi

echo "Cluster created: $CLUSTER_ID"
echo "Waiting for cluster to be ready..."

# Wait for cluster to be ready (max 5 minutes)
TIMEOUT=300
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    STATUS=$(ccloud cluster get "$CLUSTER_ID" --output json | jq -r '.state')
    if [ "$STATUS" = "READY" ]; then
        echo "Cluster is ready!"
        break
    fi
    echo "Status: $STATUS (waiting...)"
    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ $ELAPSED -ge $TIMEOUT ]; then
    echo "ERROR: Cluster did not become ready in time"
    exit 1
fi

# Get connection string
echo ""
echo "Getting connection string..."
CONNECTION_STRING=$(ccloud cluster get "$CLUSTER_ID" --output json | jq -r '.connection_string')

echo ""
echo "=== Cluster Provisioned Successfully ==="
echo "Cluster ID: $CLUSTER_ID"
echo "Connection String: $CONNECTION_STRING"
echo ""
echo "IMPORTANT: Enable vector indexing in the Cloud Console:"
echo "1. Go to https://cockroachlabs.cloud"
echo "2. Select your cluster"
echo "3. Go to Settings > Advanced"
echo "4. Verify that Vector Indexing is enabled"
echo ""
echo "Next steps:"
echo "1. Save the connection string to .env as DATABASE_URL"
echo "2. Create SQL users: cascade_app, cascade_worker, cascade_readonly"
echo "3. Run ./02_migrate.sh to create schema"
echo ""
echo "Example .env entry:"
echo "DATABASE_URL='$CONNECTION_STRING'"
