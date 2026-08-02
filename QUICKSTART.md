# CASCADE Track B - Quick Start (STUB Mode)

**No AWS/Bedrock needed!** Everything runs locally with mock data.

---

## Prerequisites

✅ Docker Desktop (you have this)  
✅ Python 3.12+ (check: `python --version`)  
✅ Git (you have this)

---

## Step 1: Start CockroachDB (One-time setup)

Open a terminal and run:

```bash
# Start CockroachDB container
docker run -d \
  --name cascade-crdb \
  -p 26257:26257 \
  -p 8080:8080 \
  cockroachdb/cockroach:latest \
  start-single-node --insecure
```

**Verify it's running:**
```bash
docker ps | grep cascade-crdb
```

You should see the container running.

---

## Step 2: Create Database & Apply Schema

```bash
# Create database
docker exec cascade-crdb ./cockroach sql --insecure \
  -e "CREATE DATABASE IF NOT EXISTS cascade;"

# Apply schema (from cockroach/ directory)
cd migrations
docker exec -i cascade-crdb ./cockroach sql \
  --insecure --database=cascade < 001_schema.sql

# Seed data
docker exec -i cascade-crdb ./cockroach sql \
  --insecure --database=cascade < 002_seed.sql

cd ..
```

---

## Step 3: Install Python Dependencies

```bash
# From cockroach/ directory
pip install -r requirements.txt
```

---

## Step 4: Verify Setup

```bash
python verify.py
```

**Expected output:**
```
✅ Environment check passed
✅ Database connection successful
✅ CASCADE_STUB_MODE=true (all functions return mock data)
✅ Ready for Track B development!
```

---

## Step 5: Test Contract Functions (Optional)

```python
# test_stub_mode.py
import asyncio
from core.contracts import retrieve, check_freshness, run_task
from uuid import uuid4

async def test_stubs():
    print("🧪 Testing STUB mode...")
    
    # Test retrieve (returns mock data)
    candidate = await retrieve("Remediate INC-1001")
    print(f"✅ retrieve() returned: {candidate}")
    
    # Test check_freshness (returns mock fresh)
    freshness = await check_freshness(uuid4())
    print(f"✅ check_freshness() returned: {freshness}")
    
    print("\n🎉 All stubs working! Track A can build against this.")

if __name__ == "__main__":
    asyncio.run(test_stubs())
```

Run it:
```bash
python test_stub_mode.py
```

---

## What's Working in STUB Mode?

✅ **All 5 MVP functions return realistic mock data:**
- `retrieve()` - returns mock playbook candidates
- `check_freshness()` - returns mock fresh results
- `run_task()` - simulates task execution
- `change_rule()` - returns mock impact
- `answer_analytics_question()` - returns mock SQL results

✅ **All 6 extension functions ready** (stubs)

✅ **Database schema loaded** (real CockroachDB locally)

✅ **No external API calls needed**

---

## Useful Commands

```bash
# Check CockroachDB status
docker ps | grep cascade-crdb

# Access SQL shell
docker exec -it cascade-crdb ./cockroach sql --insecure --database=cascade

# View CockroachDB Web UI
# Open: http://localhost:8080

# Stop CockroachDB (when done)
docker stop cascade-crdb

# Start again (after stopping)
docker start cascade-crdb

# Remove container (full reset)
docker rm -f cascade-crdb
```

---

## Troubleshooting

### Container won't start
```bash
# Check if port 26257 is already in use
netstat -an | findstr 26257

# Remove old container if exists
docker rm -f cascade-crdb
```

### Database connection fails
```bash
# Check .env has correct DATABASE_URL
# Should be: postgresql://root@localhost:26257/cascade?sslmode=disable

# Verify container is running
docker ps | grep cascade-crdb
```

### Python dependencies fail
```bash
# Use virtual environment
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate # Mac/Linux

pip install -r requirements.txt
```

---

## Next Steps

1. ✅ Your Track B is complete and ready
2. ⏳ Wait for Ashfaq to complete Track A
3. ⏳ Integration: Copy your files to Track A repo
4. ⏳ Ashfaq will handle AWS/Bedrock setup for real mode

**You're done! No AWS hassle needed for Track B.**

---

## FAQ

**Q: Do I need AWS credentials?**  
A: No! STUB mode doesn't make any AWS calls.

**Q: Do I need CockroachDB Cloud?**  
A: No! Local Docker CockroachDB is enough.

**Q: When will real AI calls work?**  
A: After Track A integration, Ashfaq will set up AWS infrastructure and switch to real mode.

**Q: Can Track A build against my stubs?**  
A: Yes! That's the whole point. Your contract functions return realistic data.

**Q: What if I want to test real Bedrock?**  
A: Set `CASCADE_STUB_MODE=false` in `.env` and add AWS credentials. But not needed for Track B completion.

---

**Status:** ✅ Track B Complete | STUB Mode | Ready for Integration
