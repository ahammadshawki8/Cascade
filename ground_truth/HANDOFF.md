# CASCADE - Handoff to Shawki

**Status:** Track A (Shell) Complete - Ready for Integration  
**Date:** August 3, 2026  
**Phase:** Days 14-16 - Integration, Testing & Deployment

---

## 🎯 Quick Start

1. **Read the handoff section** in `ground_truth/ashfaq.md` (starting at "HANDOFF TO SHAWKI")
2. **Review your progress** in `ground_truth/shawki.md`
3. **Check the spec** in `ground_truth/CASCADE_BUILD_SPEC.md` v3.1

---

## 📁 What's Here

### ✅ Complete & Ready
- **Backend API Shell** - `backend/app/routers/` (7 routers)
- **Frontend UI** - `frontend/src/` (8 components, all styled)
- **Database Schema** - `backend/migrations/` (schema + seed data)
- **Infrastructure Scripts** - `infra/` (4 scripts ready, 3 more to create)
- **Documentation** - `docs/` (placeholders for your verification)

### ⚠️ Needs Your Core Engine
- **`backend/app/core/`** - Merge your implementations here
- **`backend/worker/`** - Merge your worker code here
- **`backend/app/core/contracts.py`** - Replace `NotImplementedError` with your code

### ❌ Needs Creation
- `infra/05_deploy_lambda.sh` - Lambda worker deployment
- `infra/06_deploy_frontend.sh` - Amplify deployment
- `infra/07_deploy_cloudfront.sh` - CloudFront setup
- `README.md` - Final submission README

---

## 🚀 Your Next Steps (In Order)

1. **Merge** your core engine files into `backend/app/core/`
2. **Test** locally with `CASCADE_STUB_MODE=false`
3. **Create** remaining deployment scripts
4. **Deploy** to AWS
5. **Verify** vector index usage (Week 1 gate)
6. **Run** Agent Skills review (Week 4)
7. **Test** full demo (Cold → Guided → Cascade)
8. **Record** demo video

**Detailed instructions:** See `ground_truth/ashfaq.md` → "HANDOFF TO SHAWKI" section

---

## 📚 Documentation Structure

```
ground_truth/           # Reference docs (DO NOT DELETE)
├── ashfaq.md          # Track A progress + HANDOFF INSTRUCTIONS
├── shawki.md          # Your progress tracker
├── DAY0_CONTRACT.md   # Frozen interface contract
├── CASCADE_BUILD_SPEC.md  # Complete spec v3.1
├── Cascade_task_split.md  # Work division
└── FRONTEND_DESIGN.md # UI specifications

backend/
├── app/
│   ├── routers/       # ✅ Complete (7 routers)
│   └── core/          # ⚠️ MERGE YOUR CODE HERE
├── worker/            # ⚠️ MERGE YOUR CODE HERE
└── migrations/        # ✅ Complete (schema + seed)

frontend/
└── src/
    ├── app/           # ✅ Complete (layout + SSE)
    └── components/    # ✅ Complete (8 components)

infra/
├── 01-04_*.sh        # ✅ Complete (4 scripts)
└── 05-07_*.sh        # ❌ CREATE THESE

docs/
├── query-plans.md    # ⚠️ Fill after EXPLAIN verification
└── skills-review.md  # ⚠️ Fill after Agent Skills review
```

---

## 🔑 Critical Files for Integration

1. **`backend/app/core/contracts.py`** - Interface contract (frozen signatures)
2. **`backend/migrations/001_schema.sql`** - Complete database schema
3. **`ground_truth/DAY0_CONTRACT.md`** - Frozen decisions (D1-D7)
4. **`DEVIATIONS.md`** - Spec deviations (currently: none)

---

## ⚠️ Critical Reminders

- Vector index must use `<->` operator (L2), never `<=>` or `<#>`
- Disable `CASCADE_STUB_MODE=false` in production
- CloudFront required (ALB alone has no HTTPS)
- Bedrock model access must be manually enabled in AWS Console
- Update Secrets Manager with real CockroachDB DSNs before deployment

---

## 📞 Questions?

All answers are in `ground_truth/ashfaq.md` → "HANDOFF TO SHAWKI" section.

Good luck! The finish line is close. 🎯
