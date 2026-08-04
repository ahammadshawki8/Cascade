# Infrastructure Scripts

This directory contains scripts for provisioning and managing the AWS and CockroachDB infrastructure.

## Day 0 Setup

Run these scripts in order to complete the Day 0 setup:

1. `01_ccloud_provision.sh` - Provision CockroachDB Cloud cluster
2. `02_migrate.sh` - Run database migrations
3. `03_aws_bootstrap.sh` - Bootstrap AWS resources (ECS, Lambda, S3, SQS, etc.)

## Prerequisites

- `ccloud` CLI installed and authenticated
- AWS CLI configured with appropriate credentials
- `psql` or CockroachDB SQL client installed

## Local Development

For local development, use Docker:

```bash
docker run -d --name cockroach \
  -p 26257:26257 \
  -p 8080:8080 \
  cockroachdb/cockroach:latest \
  start-single-node --insecure
```

Then run migrations:
```bash
./02_migrate.sh
```
