"""
Setup and Quick Start Script
Checks dependencies and guides through initial setup
"""

import os
import sys
from pathlib import Path


def check_python_version():
    """Check Python version"""
    if sys.version_info < (3, 8):
        print("✗ Python 3.8 or higher is required")
        print(f"  Current version: {sys.version}")
        return False
    print(f"✓ Python version: {sys.version_info.major}.{sys.version_info.minor}")
    return True


def check_dependencies():
    """Check if required packages are installed"""
    required = ["openai", "psycopg2", "dotenv", "tqdm"]
    missing = []
    
    for package in required:
        try:
            __import__(package)
            print(f"✓ {package} installed")
        except ImportError:
            missing.append(package)
            print(f"✗ {package} NOT installed")
    
    if missing:
        print(f"\nInstall missing packages with:")
        print(f"  pip install {' '.join(missing)}")
        return False
    
    return True


def check_env_file():
    """Check if .env file exists with required keys"""
    env_file = Path(".env")
    parent_env = Path("../.env")
    
    env_path = None
    if env_file.exists():
        env_path = env_file
    elif parent_env.exists():
        env_path = parent_env
    
    if not env_path:
        print("✗ .env file not found")
        print("\nCreate .env file with:")
        print("  OPENAI_API_KEY=your_key_here")
        print("  POSTGRES_URL=postgresql://localhost:5432/bail_precedents")
        return False
    
    print(f"✓ .env file found at: {env_path}")
    
    # Check for required keys
    with open(env_path, 'r') as f:
        content = f.read()
    
    required_keys = ["OPENAI_API_KEY"]
    missing_keys = []
    
    for key in required_keys:
        if key not in content:
            missing_keys.append(key)
            print(f"  ✗ {key} not set")
        else:
            print(f"  ✓ {key} is set")
    
    if missing_keys:
        print(f"\nAdd to .env file:")
        for key in missing_keys:
            print(f"  {key}=your_value_here")
        return False
    
    return True


def check_postgres():
    """Check PostgreSQL connection"""
    try:
        import psycopg2
        from dotenv import load_dotenv
        load_dotenv()
        load_dotenv("../.env")
        
        conn_string = os.getenv("POSTGRES_URL", "postgresql://localhost:5432/bail_precedents")
        
        try:
            conn = psycopg2.connect(conn_string)
            conn.close()
            print(f"✓ PostgreSQL connection successful")
            print(f"  Connection: {conn_string.split('@')[1] if '@' in conn_string else conn_string}")
            return True
        except Exception as e:
            print(f"✗ PostgreSQL connection failed: {e}")
            print("\nSetup PostgreSQL:")
            print("  1. Install PostgreSQL from https://www.postgresql.org/download/")
            print("  2. Create database: createdb bail_precedents")
            print("  3. Set POSTGRES_URL in .env")
            return False
    
    except ImportError:
        print("✗ psycopg2 not installed")
        return False


def check_data_files():
    """Check if required data files exist"""
    files = {
        "taxonomy.json": "Taxonomy file",
        "out/": "Input case directory",
    }
    
    all_exist = True
    for path, description in files.items():
        p = Path(path)
        if p.exists():
            if p.is_dir():
                count = len(list(p.glob("*.json")))
                print(f"✓ {description}: {count} JSON files")
            else:
                print(f"✓ {description}")
        else:
            print(f"✗ {description} not found: {path}")
            all_exist = False
    
    return all_exist


def print_next_steps():
    """Print next steps"""
    print("\n" + "="*80)
    print("SETUP COMPLETE - NEXT STEPS")
    print("="*80)
    print()
    print("Run the complete pipeline:")
    print("  python run_pipeline.py --all --input-dir out --create-schema --test-case test_case.txt")
    print()
    print("Or run phases individually:")
    print("  Phase 1 (Tagging): python run_pipeline.py --phase 1 --input-dir out")
    print("  Phase 2 (Database): python run_pipeline.py --phase 2 --create-schema --clear-data")
    print("  Phase 3 (Retrieval): python run_pipeline.py --phase 3 --test-case test_case.txt")
    print()
    print("Test individual components:")
    print("  python tagger.py --input-dir out --output-dir tagged")
    print("  python analyzer.py --input test_case.txt")
    print("  python retrieval_pipeline.py --input test_case.txt --side defense")
    print()


def main():
    print("="*80)
    print("BAIL PRECEDENT SYSTEM - SETUP CHECK")
    print("="*80)
    print()
    
    checks = [
        ("Python Version", check_python_version),
        ("Dependencies", check_dependencies),
        ("Environment File", check_env_file),
        ("Data Files", check_data_files),
        ("PostgreSQL", check_postgres),
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\nChecking {name}...")
        print("-" * 40)
        result = check_func()
        results.append(result)
    
    print("\n" + "="*80)
    if all(results):
        print("✓ ALL CHECKS PASSED")
        print("="*80)
        print_next_steps()
    else:
        print("✗ SOME CHECKS FAILED")
        print("="*80)
        print("\nPlease fix the issues above and run setup.py again")
        sys.exit(1)


if __name__ == "__main__":
    main()
