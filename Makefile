# CASCADE Track B - Development Makefile

.PHONY: help install setup db-start db-stop db-reset seed test lint format clean dev

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install Python dependencies
	pip install -r requirements.txt

setup: install  ## Complete setup (install + env + db)
	@if [ ! -f .env ]; then cp .env.example .env; echo "Created .env file"; fi
	@echo "Setup complete. Edit .env if needed, then run: make db-start seed"

db-start:  ## Start local CockroachDB
	docker run -d --name cascade-crdb -p 26257:26257 -p 8080:8080 \
		cockroachdb/cockroach:latest start-single-node --insecure || \
		docker start cascade-crdb
	@echo "Waiting for database to start..."
	@sleep 3
	@docker exec cascade-crdb ./cockroach sql --insecure -e "CREATE DATABASE IF NOT EXISTS cascade;" || true
	@echo "Database ready at localhost:26257"
	@echo "Web UI at http://localhost:8080"

db-stop:  ## Stop local CockroachDB
	docker stop cascade-crdb || true

db-reset:  ## Reset database (WARNING: destroys data)
	docker stop cascade-crdb || true
	docker rm cascade-crdb || true
	@echo "Database reset. Run 'make db-start seed' to recreate."

seed:  ## Apply migrations and seed data
	@echo "Applying schema..."
	@docker exec -i cascade-crdb ./cockroach sql --insecure --database=cascade < migrations/001_schema.sql
	@echo "Seeding data..."
	@docker exec -i cascade-crdb ./cockroach sql --insecure --database=cascade < migrations/002_seed.sql
	@echo "Database seeded successfully"

test:  ## Run tests
	pytest tests/ -v

test-cov:  ## Run tests with coverage
	pytest tests/ -v --cov=core --cov=worker --cov-report=term-missing

lint:  ## Lint code
	ruff check core/ worker/ tests/

format:  ## Format code
	ruff format core/ worker/ tests/

clean:  ## Clean generated files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true

dev:  ## Start development server
	python dev_server.py

db-shell:  ## Open database shell
	docker exec -it cascade-crdb ./cockroach sql --insecure --database=cascade

db-logs:  ## Show database logs
	docker logs -f cascade-crdb

# Development workflow shortcuts

day0: setup db-start seed test  ## Complete Day 0 setup
	@echo "✅ Day 0 setup complete!"
	@echo "Next: Start developing in core/"

day1: test  ## Day 1 checkpoint (tools + llm)
	@echo "Day 1 modules: core/tools.py, core/llm.py"

day2: test  ## Day 2 checkpoint (executor explore)
	@echo "Day 2 modules: core/executor.py"

day3: test  ## Day 3 checkpoint (retrieval Phase 1) - CRITICAL GATE
	@echo "⚠️  CRITICAL: Verify vector index in docs/query-plans.md"
	@echo "Day 3 modules: core/retrieval.py"

# Check current environment
status:  ## Check development environment status
	@echo "=== CASCADE Track B Status ==="
	@echo ""
	@echo "Python version:"
	@python --version
	@echo ""
	@echo "Database status:"
	@docker ps | grep cascade-crdb || echo "Database not running (run: make db-start)"
	@echo ""
	@echo "Environment:"
	@test -f .env && echo "✅ .env exists" || echo "❌ .env missing (run: make setup)"
	@echo ""
	@echo "Stub mode:"
	@grep CASCADE_STUB_MODE .env 2>/dev/null || echo "Not configured"
