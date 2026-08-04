#!/bin/bash
# Cascade — Database Migration Script
# Day 0 Contract Step 2

set -euo pipefail

# Get DATABASE_URL from environment or .env file
if [ -z "${DATABASE_URL:-}" ]; then
    if [ -f "../.env" ]; then
        export $(grep DATABASE_URL ../.env | xargs)
    elif [ -f "../backend/.env" ]; then
        export $(grep DATABASE_URL ../backend/.env | xargs)
    else
        echo "ERROR: DATABASE_URL not set. Set it in environment or create .env file"
        exit 1
    fi
fi

MIGRATIONS_DIR="../backend/migrations"

echo "=== Running Cascade Database Migrations ==="
echo "Database: ${DATABASE_URL%%\?*}"  # Print without query params
echo ""

# Check if cockroach or psql is available
if command -v cockroach &> /dev/null; then
    SQL_CLIENT="cockroach sql --url"
elif command -v psql &> /dev/null; then
    SQL_CLIENT="psql"
else
    echo "ERROR: Neither 'cockroach' nor 'psql' client found"
    exit 1
fi

# Function to run SQL file
run_migration() {
    local file=$1
    echo "Running $(basename "$file")..."
    
    if command -v cockroach &> /dev/null; then
        cockroach sql --url "$DATABASE_URL" < "$file"
    else
        psql "$DATABASE_URL" < "$file"
    fi
    
    if [ $? -eq 0 ]; then
        echo "✓ $(basename "$file") completed"
    else
        echo "✗ $(basename "$file") failed"
        exit 1
    fi
}

# Enable vector indexing for local dev (Cloud manages this automatically)
echo "Enabling vector indexing (local dev only, will error on Cloud - this is OK)..."
if command -v cockroach &> /dev/null; then
    cockroach sql --url "$DATABASE_URL" --execute "SET CLUSTER SETTING feature.vector_index.enabled = true;" 2>/dev/null || true
else
    psql "$DATABASE_URL" -c "SET CLUSTER SETTING feature.vector_index.enabled = true;" 2>/dev/null || true
fi

# Run migrations in order
echo ""
for migration in "$MIGRATIONS_DIR"/*.sql; do
    if [ -f "$migration" ]; then
        run_migration "$migration"
        echo ""
    fi
done

echo "=== Migrations Complete ==="
echo ""
echo "Next steps:"
echo "1. Create SQL users if not already created:"
echo "   - cascade_app (read/write)"
echo "   - cascade_worker (read/write + outbox processing)"
echo "   - cascade_readonly (SELECT only, 3s statement timeout)"
echo ""
echo "2. Verify vector index exists:"
echo "   SELECT * FROM [SHOW INDEXES FROM playbooks] WHERE index_name = 'pb_embed_idx';"
echo ""
echo "3. Test connection:"
echo "   SELECT count(*) FROM rules;"
