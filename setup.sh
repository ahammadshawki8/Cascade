#!/bin/bash
# CASCADE Track B - Automated Setup Script
# Run this to set up your development environment

set -e  # Exit on error

echo "═══════════════════════════════════════════════════════════════"
echo "  CASCADE Track B - Development Environment Setup"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check prerequisites
echo "Step 1: Checking prerequisites..."
echo ""

# Check Python
if command -v python &> /dev/null; then
    PYTHON_VERSION=$(python --version 2>&1 | awk '{print $2}')
    echo -e "${GREEN}✓${NC} Python ${PYTHON_VERSION} found"
else
    echo -e "${RED}✗${NC} Python not found. Please install Python 3.12+"
    exit 1
fi

# Check Docker
if command -v docker &> /dev/null; then
    DOCKER_VERSION=$(docker --version | awk '{print $3}' | sed 's/,//')
    echo -e "${GREEN}✓${NC} Docker ${DOCKER_VERSION} found"
else
    echo -e "${RED}✗${NC} Docker not found. Please install Docker Desktop"
    exit 1
fi

# Check if Docker is running
if docker info &> /dev/null; then
    echo -e "${GREEN}✓${NC} Docker is running"
else
    echo -e "${YELLOW}⚠${NC} Docker daemon not running. Please start Docker Desktop"
    exit 1
fi

echo ""
echo "Step 2: Setting up Python environment..."
echo ""

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python -m venv venv
    echo -e "${GREEN}✓${NC} Virtual environment created"
else
    echo -e "${GREEN}✓${NC} Virtual environment already exists"
fi

# Activate virtual environment
if [ -f "venv/Scripts/activate" ]; then
    # Windows Git Bash
    source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
    # Unix/Linux
    source venv/bin/activate
else
    echo -e "${RED}✗${NC} Could not find activation script"
    exit 1
fi

echo -e "${GREEN}✓${NC} Virtual environment activated"

# Install dependencies
echo ""
echo "Installing Python dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo -e "${GREEN}✓${NC} Dependencies installed"

echo ""
echo "Step 3: Configuring environment..."
echo ""

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo -e "${GREEN}✓${NC} Created .env file"
else
    echo -e "${YELLOW}⚠${NC} .env already exists (skipping)"
fi

echo ""
echo "Step 4: Starting CockroachDB..."
echo ""

# Check if container exists
if docker ps -a | grep -q cascade-crdb; then
    echo "Container exists, starting..."
    docker start cascade-crdb &> /dev/null || true
else
    echo "Creating new container..."
    docker run -d --name cascade-crdb \
        -p 26257:26257 \
        -p 8080:8080 \
        cockroachdb/cockroach:latest \
        start-single-node --insecure
fi

# Wait for database to be ready
echo "Waiting for database to start..."
sleep 5

# Create database
docker exec cascade-crdb ./cockroach sql --insecure \
    -e "CREATE DATABASE IF NOT EXISTS cascade;" &> /dev/null

echo -e "${GREEN}✓${NC} CockroachDB running"
echo "   - SQL port: localhost:26257"
echo "   - Web UI: http://localhost:8080"

echo ""
echo "Step 5: Applying migrations..."
echo ""

# Apply schema
echo "Applying schema (001_schema.sql)..."
docker exec -i cascade-crdb ./cockroach sql --insecure --database=cascade \
    < migrations/001_schema.sql

# Seed data
echo "Seeding data (002_seed.sql)..."
docker exec -i cascade-crdb ./cockroach sql --insecure --database=cascade \
    < migrations/002_seed.sql

echo -e "${GREEN}✓${NC} Database initialized"

echo ""
echo "Step 6: Running tests..."
echo ""

pytest tests/ -v --tb=short

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓${NC} All tests passing"
else
    echo -e "${YELLOW}⚠${NC} Some tests failed (check output above)"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo -e "${GREEN}  Setup Complete!${NC}"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Next steps:"
echo ""
echo "  1. Review GETTING_STARTED.md for development workflow"
echo "  2. Check .env file and adjust if needed"
echo "  3. Start dev server: make dev"
echo "  4. Open http://localhost:8001"
echo ""
echo "Useful commands:"
echo "  make help       - Show all available commands"
echo "  make dev        - Start development server"
echo "  make test       - Run tests"
echo "  make db-shell   - Open database shell"
echo "  make status     - Check environment status"
echo ""
echo "Database access:"
echo "  Web UI:  http://localhost:8080"
echo "  SQL CLI: make db-shell"
echo ""
echo -e "${GREEN}Happy coding! 🚀${NC}"
echo ""
