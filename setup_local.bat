@echo off
REM CASCADE Track B - Local Setup (STUB Mode)
REM No AWS/Bedrock needed!

echo.
echo 🚀 CASCADE Track B - Local Setup (STUB Mode)
echo ==============================================
echo.

REM 1. Start CockroachDB
echo 📦 Starting CockroachDB container...
docker run -d --name cascade-crdb -p 26257:26257 -p 8080:8080 cockroachdb/cockroach:latest start-single-node --insecure

REM Wait for CRDB to be ready
echo ⏳ Waiting for CockroachDB to be ready...
timeout /t 5 /nobreak >nul

REM 2. Create database
echo 🗄️  Creating cascade database...
docker exec cascade-crdb ./cockroach sql --insecure -e "CREATE DATABASE IF NOT EXISTS cascade;"

REM 3. Apply migrations
echo 📋 Applying schema...
docker exec -i cascade-crdb ./cockroach sql --insecure --database=cascade < migrations/001_schema.sql

echo 🌱 Seeding data...
docker exec -i cascade-crdb ./cockroach sql --insecure --database=cascade < migrations/002_seed.sql

REM 4. Verify
echo.
echo ✅ Setup complete!
echo.
echo 📊 Access CockroachDB:
echo   • SQL Shell: docker exec -it cascade-crdb ./cockroach sql --insecure --database=cascade
echo   • Web UI: http://localhost:8080
echo.
echo 🧪 Test your setup:
echo   python verify.py
echo.
echo 🎯 Your Track B is ready in STUB mode!
echo    (No AWS/Bedrock needed - all functions return mock data)
echo.
pause
