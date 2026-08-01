#!/usr/bin/env python3
"""
CASCADE Track B - Environment Verification Script
Quick check that everything is set up correctly
"""

import sys
import os
from pathlib import Path


def check_mark(passed):
    return "✓" if passed else "✗"


def verify_environment():
    """Verify Track B environment setup"""
    
    print("=" * 60)
    print("  CASCADE Track B - Environment Verification")
    print("=" * 60)
    print()
    
    all_good = True
    
    # Check Python version
    print("1. Python Version")
    version = sys.version_info
    python_ok = version.major == 3 and version.minor >= 12
    print(f"   {check_mark(python_ok)} Python {version.major}.{version.minor}.{version.micro}")
    if not python_ok:
        print("   ⚠ Need Python 3.12+")
        all_good = False
    print()
    
    # Check directory structure
    print("2. Directory Structure")
    dirs_to_check = [
        "core",
        "worker", 
        "migrations",
        "tests",
        "docs"
    ]
    
    for dir_name in dirs_to_check:
        exists = Path(dir_name).is_dir()
        print(f"   {check_mark(exists)} {dir_name}/")
        if not exists:
            all_good = False
    print()
    
    # Check core modules
    print("3. Core Modules")
    core_modules = [
        "models.py",
        "contracts.py",
        "tools.py",
        "llm.py",
        "executor.py",
        "retrieval.py",
        "compiler.py",
        "freshness.py",
        "confidence.py",
        "cascade.py",
        "copilot.py"
    ]
    
    for module in core_modules:
        exists = Path(f"core/{module}").is_file()
        print(f"   {check_mark(exists)} core/{module}")
        if not exists:
            all_good = False
    print()
    
    # Check migrations
    print("4. Migrations")
    migrations = ["001_schema.sql", "002_seed.sql"]
    for migration in migrations:
        exists = Path(f"migrations/{migration}").is_file()
        print(f"   {check_mark(exists)} migrations/{migration}")
        if not exists:
            all_good = False
    print()
    
    # Check configuration files
    print("5. Configuration Files")
    config_files = [
        "requirements.txt",
        "pyproject.toml",
        ".env.example",
        "Makefile",
        "dev_server.py"
    ]
    
    for config in config_files:
        exists = Path(config).is_file()
        print(f"   {check_mark(exists)} {config}")
        if not exists:
            all_good = False
    
    env_exists = Path(".env").is_file()
    print(f"   {check_mark(env_exists)} .env {'(configured)' if env_exists else '(run: cp .env.example .env)'}")
    print()
    
    # Check documentation
    print("6. Documentation")
    docs = [
        "README.md",
        "GETTING_STARTED.md",
        "DAY0_CHECKLIST.md",
        "Claude.md"
    ]
    
    for doc in docs:
        exists = Path(doc).is_file()
        print(f"   {check_mark(exists)} {doc}")
        if not exists:
            all_good = False
    
    ref_dir = Path("reference").is_dir()
    print(f"   {check_mark(ref_dir)} reference/")
    print()
    
    # Try importing core modules
    print("7. Python Imports")
    try:
        from core import models, contracts
        print(f"   ✓ core.models")
        print(f"   ✓ core.contracts")
    except ImportError as e:
        print(f"   ✗ Import failed: {e}")
        print("   ⚠ Run: pip install -r requirements.txt")
        all_good = False
    print()
    
    # Check stub mode
    print("8. Stub Mode")
    try:
        stub_mode = os.getenv("CASCADE_STUB_MODE", "true")
        print(f"   ✓ CASCADE_STUB_MODE={stub_mode}")
        if stub_mode.lower() != "true":
            print("   ⚠ Consider setting to 'true' for initial development")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    print()
    
    # Final verdict
    print("=" * 60)
    if all_good:
        print("  ✓ All checks passed! Environment is ready.")
        print()
        print("  Next steps:")
        print("    1. Review GETTING_STARTED.md")
        print("    2. Complete DAY0_CHECKLIST.md")
        print("    3. Start database: make db-start")
        print("    4. Apply migrations: make seed")
        print("    5. Run tests: make test")
        print("    6. Start dev server: make dev")
    else:
        print("  ✗ Some checks failed. Review output above.")
        print()
        print("  Quick fixes:")
        print("    - Missing .env: cp .env.example .env")
        print("    - Import errors: pip install -r requirements.txt")
        print("    - Missing dirs/files: Check you're in Track_B/ directory")
    print("=" * 60)
    print()
    
    return 0 if all_good else 1


if __name__ == "__main__":
    sys.exit(verify_environment())
