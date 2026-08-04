.PHONY: help up down logs db migrate seed reset dev worker test lint fmt clean

CRDB_URL ?= postgresql://root@localhost:26257/cascade?sslmode=disable
CRDB     ?= cockroach sql --insecure --host=localhost:26257

help:
	@echo "Cascade — development commands"
	@echo ""
	@echo "  make up        Start local CockroachDB (docker compose)"
	@echo "  make down      Stop it"
	@echo "  make db        Create the cascade database + enable vector index"
	@echo "  make migrate   Apply 001_schema.sql"
	@echo "  make seed      Apply 002_seed.sql (idempotent — truncates + reseeds)"
	@echo "  make reset     db + migrate + seed, from scratch"
	@echo "  make dev       Run the API locally with hot reload"
	@echo "  make worker    Run one worker dispatch inline (no SQS/Lambda needed)"
	@echo "  make test      pytest"
	@echo "  make lint      ruff check"

up:
	docker compose up -d crdb
	@echo "waiting for CockroachDB..."
	@until docker compose exec -T crdb ./cockroach sql --insecure -e "SELECT 1" >/dev/null 2>&1; do sleep 1; done
	@echo "CockroachDB ready — console at http://localhost:8080"

down:
	docker compose down

logs:
	docker compose logs -f crdb

db:
	$(CRDB) -e "CREATE DATABASE IF NOT EXISTS cascade;"
	@# Vector indexing may be gated behind a cluster setting on a local
	@# single node. Harmless no-op on CockroachDB Cloud (spec §2).
	-$(CRDB) -e "SET CLUSTER SETTING feature.vector_index.enabled = true;" 2>/dev/null || true

migrate:
	$(CRDB) --database=cascade -f migrations/001_schema.sql
	@echo "schema applied"

seed:
	$(CRDB) --database=cascade -f migrations/002_seed.sql
	@echo "seed applied — rules at v1, 6 services, 12 incidents"

reset: db migrate seed
	@echo "local world reset"

dev:
	cd backend && uvicorn app.main:app --reload --port 8000

worker:
	cd backend && python -m worker.handler --once

test:
	cd backend && pytest -q

lint:
	cd backend && ruff check .

fmt:
	cd backend && ruff format .

clean:
	docker compose down -v
	@echo "volumes removed"
