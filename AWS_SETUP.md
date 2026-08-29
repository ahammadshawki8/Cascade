# AWS Setup, from zero to a working deployment

Everything needed to take CASCADE from "runs on my laptop" to "runs on AWS".
Written for someone who has never opened the AWS console.

Read this in order. Step 3 has a waiting period, so start it the moment you
have an account and do the rest while you wait.

**Time:** about 45 minutes of actual work, plus up to a few hours of waiting
for Bedrock model access.

---

## What you are setting up, and why

CASCADE does not need AWS to run. It ships with a deterministic local planner
and a local embedder, and with the Groq and HuggingFace keys already in
`backend/.env` it runs on real models today. AWS buys three things:

1. **Bedrock**, so the "built on AWS" claim in the submission is true rather
   than aspirational.
2. **A deployed URL**, so judges can click a link instead of cloning a repo.
3. **The $100 in activity credits** already offered to this account.

| Service | What CASCADE uses it for | Required? |
|---|---|---|
| Bedrock | Planner (Claude), embeddings (Titan) | For the AWS story |
| ECS Fargate + ECR | Runs the API container | To deploy |
| Lambda + SQS + EventBridge | Background worker and the 60s sweeper | To deploy |
| S3 | Full episode trajectories | Optional, degrades gracefully |
| Secrets Manager | The three database connection strings | To deploy |
| CloudFront | HTTPS in front of the load balancer | To deploy |
| Amplify | Hosts the frontend | To deploy |
| IAM | The deploy scripts create roles | To deploy |

---

## Step 1: create the AWS account

Skip if you already have one. Note that CASCADE also needs a **CockroachDB
Cloud** account, which is a separate company and a separate signup. See the
CockroachDB section near the end.

1. Go to `https://aws.amazon.com` and choose **Create an AWS Account**
2. Give an email address and an account name. The email becomes the **root
   user**, which owns billing and can never be scoped down, so use one you
   control long term
3. Choose **Personal** account type
4. Enter address and phone number
5. **A credit or debit card is required**, even on the free tier. AWS places a
   small temporary authorisation (about $1) and refunds it
6. Verify by SMS or voice call
7. Choose the **Basic support plan**, which is free

Activation usually takes a few minutes but can take a few hours. You will get
an email when it completes.

---

## Step 2: secure the account before doing anything else

This takes five minutes and prevents the single worst outcome, which is a
leaked root credential on an account with a card attached.

### 2a. Turn on MFA for the root user

1. Sign in as root
2. Top right, your account name, **Security credentials**
3. **Multi-factor authentication (MFA)**, then **Assign MFA device**
4. Use an authenticator app (Google Authenticator, Authy, 1Password)

### 2b. Create an admin IAM user and stop using root

Root should be used for billing and almost nothing else.

1. Go to the **IAM** console
2. **Users**, then **Create user**
3. Name it something like `cascade-admin`
4. Tick **Provide user access to the AWS Management Console** if you want a
   separate console login
5. **Attach policies directly**, choose **AdministratorAccess**

   For a hackathon with a deadline this is the pragmatic choice. The
   least-privilege alternative is in the appendix.
6. Create the user, then enable MFA on it too

### 2c. Set a budget before you spend anything

Do this now, not later. The load balancer and the Fargate task bill by the hour
whether or not anyone is using them.

1. **Billing and Cost Management** console, then **Budgets**
2. **Create budget**, choose **Zero spend budget** or a **Monthly cost budget**
   of, say, $20
3. Point the alert at your email

This is also one of the five paid activities, so you get $20 of credit for
doing something you should do anyway.

---

## Step 3: request Bedrock model access, NOW

**Do this before anything else technical.** Access is granted manually, per
account and per region, and approval is not instant. Until it lands, every
Bedrock call returns `AccessDeniedException`, which looks exactly like a
credentials problem but is not.

1. Switch the console region to **us-east-1 (N. Virginia)**, top right

   us-east-1 has the widest Bedrock model selection, and it is what
   `backend/.env` already pins as `AWS_REGION`.
2. Open the **Amazon Bedrock** console
3. Left nav, **Model access**. In newer console layouts it sits under
   **Configurations**, sometimes labelled **Model catalog**
4. **Enable specific models** (or **Modify model access**)
5. Tick:
   - The **Anthropic Claude** models, both a large one and a small fast one
   - **Amazon Titan Text Embeddings V2**
6. Anthropic models require a short use-case form. Say it is a hackathon
   project for automated incident response. Submit
7. Titan is usually granted instantly. Anthropic can take minutes to hours

Refresh the Model access page until status reads **Access granted**.

While you wait, continue with step 4.

---

## Step 4: install the AWS CLI

The seven deploy scripts in `infra/` all shell out to `aws`, so this is
required regardless of which credential method you choose.

**Windows (PowerShell):**
```powershell
winget install --id Amazon.AWSCLI -e
```

**macOS:**
```bash
brew install awscli
```

**Linux:**
```bash
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscli.zip
unzip awscli.zip && sudo ./aws/install
```

Close and reopen the terminal, then confirm:
```bash
aws --version
```

---

## Step 5: get credentials onto your machine

Two options. Pick one.

CASCADE calls `boto3.Session()` and uses the **default credential chain**, so
it picks up whatever the AWS CLI is configured with. You do **not** put the
access key in `backend/.env`.

### Option A: IAM Identity Center (recommended)

Issues **temporary** credentials that expire, so there is no long-lived secret
sitting on disk. Slightly more setup, meaningfully safer.

```bash
aws configure sso
```

It prompts for a start URL and region, opens a browser to approve, and lets you
name a profile. Refresh later with:

```bash
aws sso login --profile <name>
```

If a profile is not the default, either export it or pass it explicitly:

```bash
export AWS_PROFILE=<name>          # macOS / Linux
$env:AWS_PROFILE = "<name>"        # PowerShell
```

### Option B: IAM user access key (simpler)

1. IAM console, **Users**, open `cascade-admin`
2. **Security credentials** tab, **Create access key**
3. Use case: **Command Line Interface (CLI)**. Acknowledge the warning
4. **Copy the secret access key now.** It is shown exactly once and cannot be
   retrieved later
5. Configure:

```bash
aws configure
```

| Prompt | Value |
|---|---|
| AWS Access Key ID | the key ID, starts `AKIA` |
| AWS Secret Access Key | the secret |
| Default region name | `us-east-1` |
| Default output format | `json` |

This writes `~/.aws/credentials`, which is outside the repo and therefore
cannot be committed by accident.

> **Never create access keys on the root user.** A root key cannot be scoped,
> is awkward to rotate, and owns billing. If your only login is root, create
> the IAM user in step 2b first and key that instead.

---

## Step 6: verify

### Are credentials resolving?

```bash
aws sts get-caller-identity
```

Expect JSON with `UserId`, `Account` and `Arn`. If this fails, nothing below
will work.

### Did Bedrock model access actually land?

```bash
aws bedrock list-foundation-models --region us-east-1 \
  --query 'modelSummaries[?contains(modelId,`anthropic`) || contains(modelId,`titan-embed`)].modelId'
```

Note this is the `bedrock` control plane, not `bedrock-runtime`.

### Check the model IDs

`backend/.env` pins:

```bash
BEDROCK_AGENT_MODEL_ID=anthropic.claude-sonnet-5
BEDROCK_FAST_MODEL_ID=anthropic.claude-haiku-4-5
BEDROCK_EMBED_MODEL_ID=amazon.titan-embed-text-v2:0
```

All three are correctly formed. On the current Bedrock Messages API a Claude
model ID is the plain first-party id with an `anthropic.` prefix and no date
suffix, so `anthropic.claude-sonnet-5` is exactly right. The dated form
(`anthropic.claude-3-5-sonnet-20241022-v2:0`) belongs to the older
`InvokeModel` / `Converse` integration, which uses a different request shape
and is not what this project calls.

Still confirm the three are present in `list-foundation-models` output for the
account and region, since availability varies. A model ID that is genuinely
wrong fails with `ValidationException`, which is easy to misread as a
permissions problem.

### Ask the application itself

Restart the backend, then:

```bash
curl localhost:8000/api/admin/smoke -H "x-admin-token: dev-admin-token"
```

You want:

```json
{
  "chat_provider": "bedrock",
  "embed_provider": "bedrock",
  "llm_status": "ok"
}
```

In the UI, the status bar dot goes from amber `groq` to green `bedrock`, and
the "Fallback provider" banner disappears.

If it still says `groq`, Bedrock was not usable and the chain fell back
silently by design. Check the backend log for a line beginning
`bedrock unavailable:`, which names the actual reason.

---

## Step 7: deploy

Only after step 6 passes.

```bash
cd infra

./01_ccloud_provision.sh     # CockroachDB Cloud cluster
./02_migrate.sh              # schema, seed, vector index

./03_aws_bootstrap.sh        # S3, SQS, Secrets Manager, IAM, ECR

# Store the real connection strings BEFORE anything tries to connect
aws secretsmanager update-secret --secret-id cascade/dsn-app      --secret-string "postgresql://..."
aws secretsmanager update-secret --secret-id cascade/dsn-worker   --secret-string "postgresql://..."
aws secretsmanager update-secret --secret-id cascade/dsn-readonly --secret-string "postgresql://..."

./04_deploy_ecs.sh           # image to ECR, load balancer, Fargate service
./05_deploy_lambda.sh        # worker, SQS trigger, 60s EventBridge sweeper
./07_deploy_cloudfront.sh    # HTTPS in front of the load balancer
./06_deploy_frontend.sh      # Amplify, built against the CloudFront URL
```

**`07` runs before `06`. This is not a typo.** `NEXT_PUBLIC_API_URL` is baked
into the frontend bundle at build time, so the CloudFront URL has to exist
before the build starts. Amplify serves https, so pointing the frontend at the
raw http load balancer gets every request blocked as mixed content, taking the
live event stream with it. `06` refuses to build against a non-https URL for
exactly this reason.

To put a password on the deployed site:

```bash
DEMO_USER=judge DEMO_PASSWORD=<something> ./06_deploy_frontend.sh
```

Worth knowing: CASCADE has authorization but **no authentication**. Anyone who
can reach the deployed site can change policy or reset the demo. For a judging
link that is arguably intended. If the link goes wider than that, set the
password above.

### Verify the deployment

```bash
curl https://<cloudfront>/health
curl https://<cloudfront>/api/admin/verify-index -H "x-admin-token: $ADMIN_TOKEN"
curl https://<cloudfront>/api/admin/smoke        -H "x-admin-token: $ADMIN_TOKEN"
curl -N https://<cloudfront>/api/events          # must stream, not buffer
```

The last one matters. If `/api/events` returns one buffered blob at the end
instead of streaming, CloudFront compression got re-enabled and the dashboard
will silently receive nothing.

---

## The $100 in activity credits

Five activities, $20 each. Do them in this order.

| Order | Activity | Notes |
|---|---|---|
| 1 | **Bedrock playground** | Do first. Overlaps exactly with what the project needs, and it is the natural moment to request model access |
| 2 | **AWS Budgets** | Set a real budget. You need one anyway |
| 3 | **Lambda web app** | We deploy a Lambda worker in `infra/05`, so this is close to real work |
| 4 | EC2 | Not used by this project, which runs on Fargate. Launch a `t2.micro`, claim the credit, **terminate it immediately** |
| 5 | RDS / Aurora | Not used, since we run CockroachDB. Smallest instance, claim, **delete immediately** |

$100 comfortably covers Bedrock for a demo. Titan embeddings are roughly $0.02
per million tokens, and a full demo run costs cents.

**Terminate the EC2 and RDS instances the moment the credit is confirmed.** An
idle `db.t3.micro` left running is the most common way to burn a credit balance
on nothing.

---

## CockroachDB Cloud (separate from AWS)

CASCADE needs a CockroachDB cluster in addition to AWS. This is a different
company and a different signup.

There is already a `COCKROACH_API_KEY` in `backend/.env` and it authenticates
correctly, but **it is a Cloud management API key, not a database credential**,
and there are currently **zero clusters provisioned** on that account.

To finish:

1. Sign in at `https://cockroachlabs.cloud`
2. Create a cluster. The free **Basic** tier is enough for a single-region demo
3. Create the three SQL users the project expects: `cascade_app`,
   `cascade_worker`, `cascade_readonly`

   `cascade_readonly` is what makes the Ops Copilot safe. It must hold **no**
   write grants, because that is the last line of defence behind the SQL
   validator.
4. Copy each connection string into Secrets Manager as shown in step 7. They
   must use `sslmode=verify-full`
5. Run `infra/02_migrate.sh` against the new cluster
6. Re-prove the vector index on Cloud:

```bash
curl https://<cloudfront>/api/admin/verify-index -H "x-admin-token: $ADMIN_TOKEN"
```

Expect `uses_index: true` and a plan naming `pb_embed_idx`. This was verified
locally but has never been proven on a Cloud cluster, and the whole distributed
vector search claim rests on it.

Note that `infra/01_ccloud_provision.sh` currently only prints console
instructions. It does not call the Cloud API, so the `CCDB1_` key is unused by
the codebase as it stands.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Unable to locate credentials` | CLI not configured, or the wrong profile | `aws configure`, or set `AWS_PROFILE` |
| `AccessDeniedException` from Bedrock | Model access not granted yet | Finish step 3 and wait for **Access granted** |
| `ValidationException` from Bedrock | Wrong model ID | Copy exact IDs from `list-foundation-models` |
| Smoke test still says `groq` | Bedrock unusable, chain fell back by design | Backend log line `bedrock unavailable:` names the reason |
| Model not listed in your region | Bedrock availability varies by region | Use `us-east-1`, and make sure `AWS_REGION` agrees |
| `ExpiredToken` | SSO session lapsed | `aws sso login --profile <name>` |
| Lambda dies at import | Host wheels for the database driver | `05` already pins `manylinux2014_x86_64`. Do not remove those flags |
| `/api/events` returns one blob | CloudFront compression re-enabled | `07` sets `Compress: false` deliberately |
| Frontend loads, no data | Built against http instead of https | Re-run `07` then `06`, in that order |

---

## Security rules, non-negotiable

1. **Never commit credentials.** `backend/.env`, `frontend/.env.local` and
   `~/.aws/credentials` are all outside version control. `.gitignore` covers
   the first two; the third is outside the repo entirely
2. **Never put a secret in a `NEXT_PUBLIC_` variable.** Those are inlined into
   the client bundle at build time. This project had exactly that bug once: the
   admin token was read out of Secrets Manager in order to publish it in the
   page source. It is fixed by a server-side proxy. Do not undo it
3. **Never key the root user.** Use an IAM user or Identity Center
4. **Rotate anything that leaks.** In IAM, deactivate the key first rather than
   deleting it, so you can confirm nothing legitimate breaks, then delete
5. **Keep the budget alert on** for the whole project

---

## Checklist

Copy this into an issue and tick as you go.

```
[ ] AWS account created and activated
[ ] Root MFA enabled
[ ] IAM admin user created, MFA enabled
[ ] Budget alert set
[ ] Bedrock model access REQUESTED          <- do on day one, it waits
[ ] AWS CLI installed
[ ] Credentials configured
[ ] aws sts get-caller-identity works
[ ] Bedrock model access GRANTED
[ ] Exact model IDs copied into backend/.env
[ ] /api/admin/smoke reports bedrock, llm_status ok
[ ] CockroachDB Cloud cluster created
[ ] Three SQL users created
[ ] Connection strings in Secrets Manager
[ ] infra 01 through 07 executed in the right order
[ ] Deployment verified, including that /api/events streams
[ ] Vector index re-proven on the Cloud cluster
[ ] Latency re-measured on Bedrock, README and CLAUDE.md updated
[ ] $100 credits claimed, EC2 and RDS instances terminated
[ ] Demo video recorded
[ ] Devpost submitted
```

---

## Appendix: least-privilege IAM

If you would rather not grant `AdministratorAccess`, these are the managed
policies that cover what the deploy scripts do. Attach them to a dedicated
deploy user.

| Policy | Covers |
|---|---|
| `AmazonBedrockFullAccess` | Planner and embeddings |
| `AmazonECS_FullAccess` | Fargate service and cluster |
| `AmazonEC2ContainerRegistryFullAccess` | Pushing the image |
| `AWSLambda_FullAccess` | Worker function |
| `AmazonSQSFullAccess` | Event queue |
| `AmazonS3FullAccess` | Episode storage |
| `SecretsManagerReadWrite` | The three connection strings |
| `CloudFrontFullAccess` | HTTPS distribution |
| `AdministratorAccess-Amplify` | Frontend hosting |
| `AmazonEventBridgeFullAccess` | The 60s sweeper |
| `IAMFullAccess` | The scripts create execution roles |
| `AmazonVPCFullAccess` | Load balancer and security groups |

`IAMFullAccess` is the uncomfortable one, and it is genuinely needed because
the scripts create task and execution roles. If that is unacceptable, create
the roles by hand first and strip IAM from the deploy user.

---

**Next:** work top to bottom. The only thing with a real waiting period is
Bedrock model access in step 3, so start it early. Everything else is
mechanical.
