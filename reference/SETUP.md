# CASCADE — Technical Requirements & Setup Guide

**Companion to `CASCADE_BUILD_SPEC.md` (v3.1).** The build spec says *what to build*. This document says *what to have ready before you start building*, with exact versions, accounts, and a readiness gate.

Target machine: **Windows 11** (your environment). Everything below is specified for it.

---

## 0. The stack, in one table (the direct answer)

| Question | Answer | Why this and not the alternative |
|---|---|---|
| **Which cloud?** | **AWS**, region **`us-east-1`** | Contest requires ≥1 AWS service. `us-east-1` has the widest Bedrock model availability and every service in this stack. Do not use another region — Bedrock model access and CockroachDB cluster region must match to avoid cross-region latency on every LLM call. |
| **Which database?** | **CockroachDB Cloud** (serverless/free tier), one database `cascade` | Contest requirement. Also genuinely right: distributed vector index + strict serializable transactions in one engine is exactly what the provenance/freshness design needs. |
| **Backend framework?** | **FastAPI** (Python 3.12) + `uvicorn` | Async-native (the executor is an async loop with an in-process event bus), first-class SSE, Pydantic v2 validation for the PlaybookSpec compiler gate. Django is too heavy; Flask lacks native async. |
| **Frontend framework?** | **Next.js 14** (App Router) + TypeScript + Tailwind + `shadcn/ui` | Single dashboard route; `shadcn/ui` gives production-looking cards/dialogs/toasts in hours, which matters for the demo video. Deployed as a static build on Amplify. |
| **LLM?** | **Amazon Bedrock** — Claude Sonnet 5 (agent + compiler), Claude Haiku 4.5 (cheap calls), Titan Text Embeddings V2 (vectors) | Contest wants AWS services; Bedrock keeps LLM traffic inside the same IAM/VPC story as everything else. Accessed via `AnthropicBedrockMantle` (the Messages-API Bedrock client), not raw `InvokeModel`. |
| **Compute?** | **ECS Fargate** (1 task) behind **ALB**, fronted by **CloudFront** for HTTPS | See §6 for the one open decision (App Runner alternative). |
| **Async worker?** | **AWS Lambda** (Python 3.12), triggered by **SQS** + **EventBridge** (60s sweeper) | Transactional outbox relay. Lambda free tier covers the entire hackathon. |
| **Language versions** | Python **3.12**, Node **20 LTS**, TypeScript **5.x** | Lambda's newest stable Python runtime is 3.12 — matching local avoids "works locally, fails in Lambda". Next.js 14 needs Node ≥18.17; 20 LTS is the safe choice. |

**Full AWS service list you will touch:** Bedrock · ECS Fargate · ECR · ALB · CloudFront · Lambda · SQS (+DLQ) · SNS (optional) · EventBridge · S3 · Secrets Manager · IAM · Amplify Hosting · CloudWatch Logs.

---

## Part A — Accounts to create

Do these first. Two of them have provisioning delays that can cost you a day if you discover them in Week 3.

| # | Account | Cost | Time to ready | Notes |
|---|---|---|---|---|
| A1 | **AWS account** | Card required; see §5 for forecast | 10 min + verification | ⚠️ **Do not build with the root user.** After signup: enable MFA on root, create an IAM user `cascade-dev` with `AdministratorAccess`, generate access keys for that user, and use those everywhere. |
| A2 | **Bedrock model access** (inside AWS) | — | **minutes → 24h** | ⚠️ **THE #1 BLOCKER.** Console → Bedrock → Model access → Manage model access → enable **Anthropic Claude (Sonnet + Haiku)** and **Amazon Titan Text Embeddings V2**. Anthropic models may require a short use-case form. Until this is granted, every LLM call fails with `AccessDeniedException`. Request it on day one, before writing any code. |
| A3 | **CockroachDB Cloud** | Free tier (monthly credits) | 15 min | Sign up, create a **serverless cluster on AWS `us-east-1`** named `cascade`. Then verify two things (spec §12 step 0): `CREATE VECTOR INDEX` succeeds, and the cluster page exposes the **Managed MCP Server** config snippet. If either is missing on free tier, use the smallest paid/trial tier and record it in `DEVIATIONS.md`. |
| A4 | **GitHub account + public repo** | Free | 5 min | Create `cascade` as **public** immediately, add the MIT `LICENSE` file, and set the license in the repo's **About** panel (contest requirement — judges check this). Push from day one; visible commit history helps. |
| A5 | **Devpost account + hackathon registration** | Free | 5 min | Register at the contest page now so you can see the submission form fields early and draft answers as you go. |
| A6 | **YouTube account** | Free | 5 min | For the <3 min demo video. Must be set **Public** (not Unlisted) and tested logged-out. |

---

## Part B — Local machine setup (Windows 11)

### B0. Choose your shell environment first (do this before anything else)

`infra/scripts/*.sh` are bash. You have two workable paths:

| Path | Setup | Recommendation |
|---|---|---|
| **WSL2 + Ubuntu** (recommended) | Install WSL2, keep the repo at `~/cascade` **inside** the Linux filesystem, use VS Code's *WSL* remote extension | One consistent Unix environment for Python, Node, Docker, and the bash scripts. Fewest surprises. |
| **Native Windows + Git Bash** | Python/Node installed on Windows, run `.sh` files via Git Bash | Fine if you prefer it. Slightly more friction with Docker networking and path handling. |

⚠️ **If you use WSL2, do not keep the repo on `/mnt/c/...`** — cross-filesystem I/O is extremely slow and will make `npm install` and pytest crawl.

⚠️ **Line endings (both paths):** add a `.gitattributes` at repo root on day one, or your bash scripts will fail with `$'\r': command not found`:
```gitattributes
* text=auto eol=lf
*.sh text eol=lf
```

### B1. Toolchain to install

| Tool | Version | Install (Windows / WSL) | Verify |
|---|---|---|---|
| **Git** | latest | `winget install Git.Git` | `git --version` |
| **Python** | **3.12.x** | `winget install Python.Python.3.12` / `sudo apt install python3.12 python3.12-venv` | `python --version` |
| **uv** (fast Python package manager) | latest | `pip install uv` — optional but recommended over pip/venv | `uv --version` |
| **Node.js** | **20 LTS** | `winget install OpenJS.NodeJS.LTS` / `nvm install 20` | `node --version` |
| **Docker Desktop** | latest, **WSL2 backend enabled** | `winget install Docker.DockerDesktop` | `docker run hello-world` |
| **AWS CLI** | **v2** | `winget install Amazon.AWSCLI` | `aws --version` |
| **ccloud CLI** | latest | Download from CockroachDB Cloud docs (or `brew`/`curl` install inside WSL) | `ccloud version` |
| **CockroachDB binary** | latest | Download the Windows/Linux binary — gives you `cockroach sql` as your SQL client | `cockroach version` |
| **VS Code** | latest | Already installed | + extensions: Python, Pylance, Ruff, Tailwind CSS IntelliSense, WSL (if using WSL) |
| **Claude Code** | latest | Already installed | Needed for the **MCP dev-workflow demo beat** (D6/D8) |

You do **not** need a separate `psql` — `cockroach sql --url "<connection-string>"` works against both local and Cloud, and `02_migrate.sh` can call it.

### B2. Media tools (for the deliverables — install now, not in Week 5)

| Tool | Purpose | Cost |
|---|---|---|
| **OBS Studio** | Screen recording for the demo video **and the weekly fallback footage (D8)** | Free |
| **ShareX** (or Windows Snip & Sketch) | Hero GIF for the README | Free |
| **Clipchamp** (built into Win 11) or **DaVinci Resolve** | Video editing, trimming to <3:00 | Free |
| **draw.io** (web or desktop) | `docs/architecture.png` | Free |

### B3. Configure credentials

```bash
aws configure            # IAM user cascade-dev keys, region us-east-1, output json
aws sts get-caller-identity          # must return the cascade-dev user, not root
ccloud auth login
```

Then verify Bedrock access actually works (this is the real test of A2):
```bash
aws bedrock list-foundation-models --region us-east-1 --query "modelSummaries[?contains(modelId,'claude')].modelId"
```

### B4. Local CockroachDB

```bash
docker run -d --name crdb -p 26257:26257 -p 8080:8080 \
  cockroachdb/cockroach:latest start-single-node --insecure
cockroach sql --insecure --host=localhost:26257 -e "CREATE DATABASE cascade;"
```
DB console at `http://localhost:8080`. If `CREATE VECTOR INDEX` errors as a disabled feature, run `SET CLUSTER SETTING feature.vector_index.enabled = true;` first (spec §2).

---

## Part C — AWS pre-flight (before Week 1 coding)

| # | Item | Why it matters |
|---|---|---|
| C1 | **Bedrock model access granted** (A2) and smoke-tested with one real Claude call + one Titan embed call | Everything downstream is blocked on this |
| C2 | **Billing alarm** at $50 (CloudWatch → Billing → Create alarm) | You will not notice a runaway ECS task otherwise |
| C3 | **Budget** in AWS Budgets set to your comfort ceiling with email alerts | Second safety net |
| C4 | Confirm **service quotas** are default-sufficient: ECS Fargate tasks (default fine), Lambda concurrency (default 1000, you reserve 2) | Fresh accounts occasionally have low limits |
| C5 | Decide whether ECS runs 24/7 (see §5 cost note — recommendation: **no**, deploy in Week 4) | Biggest cost lever |

---

## Part D — Project dependencies (exact package lists)

### D1. Backend — `backend/pyproject.toml`

```toml
[project]
name = "cascade-backend"
requires-python = ">=3.12,<3.13"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "psycopg[binary,pool]>=3.2",      # CockroachDB over the Postgres wire protocol
  "pydantic>=2.9",
  "pydantic-settings>=2.6",          # env parsing per spec §2.1.3
  "anthropic[bedrock]>=0.40",        # AnthropicBedrockMantle client for Claude on Bedrock
  "boto3>=1.35",                     # Titan embeddings, S3, SQS, SNS, Secrets Manager
  "sse-starlette>=2.1",              # SSE endpoint
  "httpx>=0.27",                     # Lambda -> /internal/sse bridge
  "python-json-logger>=2.0",         # structured logs into CloudWatch
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "ruff>=0.7",
  "python-dotenv>=1.0",
]
```

Install: `uv pip install -e ".[dev]"` (or `pip install -e ".[dev]"` in a venv).

### D2. Frontend — `frontend/package.json` (key deps)

```
next@14  react@18  react-dom@18  typescript@5
tailwindcss  postcss  autoprefixer
class-variance-authority  clsx  tailwind-merge  lucide-react   # shadcn/ui prerequisites
sonner                                                          # toasts for cascade events
@radix-ui/react-dialog  @radix-ui/react-collapsible  @radix-ui/react-progress
```

Bootstrap:
```bash
npx create-next-app@14 frontend --typescript --tailwind --app --eslint
cd frontend && npx shadcn@latest init
npx shadcn@latest add card badge button dialog input progress collapsible sonner table
```

SSE needs no library — the browser's built-in `EventSource` is what the spec expects.

### D3. Backend container — `backend/Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .
COPY app/ ./app/
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```
⚠️ Build for **`linux/amd64`** (`docker build --platform linux/amd64`) — Fargate rejects arm64 images built on an arm host.

### D4. Local orchestration — `docker-compose.yml`

Services: `crdb` (single-node, ports 26257/8080) and optionally `api` (built from `backend/`, port 8000, `DATABASE_URL` pointing at `crdb`). Frontend runs via `npm run dev` on :3000 with `NEXT_PUBLIC_API_URL=http://localhost:8000`. This is the whole local loop — no SQS/Lambda needed locally (worker runs inline via `python -m worker.handler --once`, spec §2.1.4).

### D5. CI — `.github/workflows/test.yml`

⚠️ CockroachDB **cannot** be a GitHub Actions `services:` container (you can't override its command). Start it with an explicit step:
```yaml
- run: |
    docker run -d -p 26257:26257 cockroachdb/cockroach:latest start-single-node --insecure
    for i in {1..30}; do docker exec $(docker ps -q) ./cockroach sql --insecure -e "SELECT 1" && break || sleep 2; done
```

---

## Part E — Cost forecast (5 weeks) and how to keep it small

| Service | If you deploy in Week 4 only (recommended) | If you leave it running from Week 1 |
|---|---|---|
| ALB | ~$8 | ~$25 |
| ECS Fargate (0.5 vCPU / 1 GB) | ~$6 | ~$22 |
| CloudFront | ~$0 (free tier: 1 TB out) | ~$0 |
| Lambda + SQS + EventBridge | ~$0 (free tier) | ~$0 |
| S3 + Secrets Manager | ~$3 | ~$4 |
| Amplify Hosting | ~$0–1 (free tier) | ~$1 |
| CockroachDB Cloud | $0 (free tier) | $0 |
| **Bedrock (the real variable)** | **$30–100** | **$30–100** |
| **Total** | **≈ $50–120** | **≈ $80–150** |

**Five levers that actually matter:**
1. **Develop locally; deploy to AWS in Week 4.** ALB + ECS are the only meaningfully-priced always-on resources. This alone saves ~$30.
2. **Scale ECS to `desired-count=0` when you're not demoing.** One CLI command; ALB still costs but compute stops.
3. **Use Haiku for the cheap calls** (precondition, param extraction, recheck) — the spec already pins this. It's ~5× cheaper than Sonnet and these are the highest-frequency calls.
4. **Cache Bedrock responses during development.** The test suite already uses recorded fixtures (spec §11) — use them instead of live calls while iterating on non-LLM code.
5. **Keep the 15-step / 25k-token budget caps enforced from day one** (spec §5.4). A runaway agent loop is the one way to get a surprising bill.

---

## Part F — The one architecture decision still open

**ECS + ALB + CloudFront** (current spec) vs **AWS App Runner**.

App Runner gives you `https://xxxx.us-east-1.awsapprunner.com` out of the box — it would eliminate the ALB, the CloudFront distribution, and the entire mixed-content problem that v3.1 of the spec exists to solve, at similar or lower cost.

| | ECS + ALB + CloudFront (spec default) | App Runner |
|---|---|---|
| HTTPS | Requires CloudFront in front (the v3.1 fix) | Built in |
| Setup effort | ~40 lines in `03_aws_bootstrap.sh`, run once | ~10 lines |
| Compliance table | Names **ECS**, which is on the contest's own service list | Names App Runner (not on the list — but you already qualify via Bedrock, Lambda, S3) |
| Cost | ALB ~$16/mo floor | ~$5/mo floor + usage |

**Recommendation: keep ECS + ALB + CloudFront.** It's already fully specified and scripted, and naming ECS reads well on the compliance table. **But** if CloudFront wiring consumes more than half a day in Week 4, switch to App Runner without hesitation and record it in `DEVIATIONS.md` — you lose nothing that judges score, and a working HTTPS demo beats an elegant one that doesn't load.

---

## Part G — Where the learning curve actually is

You've built complex logic systems before, so the algorithmic core here (provenance graph, freshness join, retrieval ranking, confidence math) is the part you'll find easy. Budget your learning time for these instead:

| Area | Likely friction | Mitigation |
|---|---|---|
| **AWS IAM** | Least-privilege policies are fiddly; you'll hit `AccessDenied` from a missing action | Start with broad policies to get it working, tighten in Week 5's hardening pass. Write the errors down — the fix is almost always one missing action string. |
| **ECS/Fargate first deploy** | Task fails to start, health check fails, image architecture mismatch | Deploy a hello-world container **in Week 1** as a spike, before you have real code. Discovering `--platform linux/amd64` at 2am in Week 4 is the bad path. |
| **SSE through CloudFront** | Buffering or premature connection close | The spec already handles it (CachingDisabled + 60s origin timeout + 15s heartbeats). Test the SSE path immediately after the first CloudFront deploy, not at the end. |
| **Async Python** (`asyncio.Event`, background tasks, async psycopg) | Silent hangs from a missed `await`, or blocking calls inside the event loop | Never call `boto3` (synchronous) directly in a request handler without `run_in_executor`, or it stalls the whole service. |
| **Bedrock tool-use loop shape** | Message/tool_result round-trip formatting | Follow the Anthropic SDK's tool-use pattern exactly; get one loop working end-to-end before adding budgets/interrupts on top. |

---

## Part H — Readiness checklist

You are ready to start **Week 1** when every box is checked:

**Accounts**
- [ ] AWS account created; root has MFA; IAM user `cascade-dev` created with access keys
- [ ] **Bedrock model access GRANTED** for Claude Sonnet, Claude Haiku, Titan Embeddings V2 in `us-east-1`
- [ ] CockroachDB Cloud cluster `cascade` running on AWS `us-east-1`
- [ ] CockroachDB **vector index verified working** on that cluster
- [ ] CockroachDB **Managed MCP Server config snippet located** in the Cloud Console
- [ ] Public GitHub repo created with MIT `LICENSE` **and license set in the About panel**
- [ ] Devpost account registered for the hackathon
- [ ] YouTube account ready

**Machine**
- [ ] Shell environment chosen (WSL2 or Git Bash) and `.gitattributes` with `eol=lf` committed
- [ ] Python 3.12, Node 20, Docker Desktop, AWS CLI v2, ccloud, cockroach binary — all verified
- [ ] `aws sts get-caller-identity` returns `cascade-dev` (not root)
- [ ] Local CockroachDB running in Docker; `cascade` database created
- [ ] OBS Studio installed and one test recording made

**Cost guards**
- [ ] Billing alarm at $50 configured
- [ ] AWS Budget with email alerts configured

**Smoke tests (the real gate)**
- [ ] One live Claude call through `AnthropicBedrockMantle` returns text
- [ ] One live Titan V2 embed call returns a 1024-dim vector
- [ ] `CREATE VECTOR INDEX` succeeds on the local Docker CockroachDB
- [ ] Claude Code connected to the cluster via the Managed MCP Server, and you ran one query through it (this is also your first piece of **demo footage** — record it)
- [ ] A hello-world container deployed to ECS Fargate and reachable (the Week-1 infra spike)

When the last box is checked, open `CASCADE_BUILD_SPEC.md` at **§14 Week 1** and start building.

---

## Quick reference — what you'll be doing in each week

| Week | Primary tool you're living in | Deliverable that must exist by Friday |
|---|---|---|
| 1 | Python/FastAPI + `cockroach sql` + Claude Code (MCP) | Explore loop works end-to-end; `docs/query-plans.md` proves vector index usage; MCP footage recorded |
| 2 | Python (compiler + retrieval) | Guided run ≥3× faster than cold, visible in `/api/metrics` |
| 3 | Python (worker) + AWS console (SQS/Lambda) | Full learn→reuse→unlearn path works; rough fallback footage recorded |
| 4 | TypeScript/Next.js + AWS deploy scripts | Public HTTPS demo URL; a stranger completes the README 5-minute tour |
| 5 | OBS + Clipchamp + README | Video <3:00 public; Devpost submitted by **Aug 16, 5:00 PM EDT** |

*End of setup guide.*
