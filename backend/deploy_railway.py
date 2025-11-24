#!/usr/bin/env python3
"""
Railway Deployment Script
Handles database migrations and setup for Railway deployment
"""

import os
import sys
import subprocess
import time
from pathlib import Path

# We're already in the backend directory
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

def run_command(cmd, cwd=None, check=True):
    """Run a command and return the result"""
    print(f"🔧 Running: {cmd}")
    try:
        result = subprocess.run(
            cmd, 
            shell=True, 
            cwd=cwd or backend_dir,
            capture_output=True, 
            text=True,
            check=check
        )
        if result.stdout:
            print(f"✅ Output: {result.stdout.strip()}")
        return result
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}")
        if e.stderr:
            print(f"❌ Stderr: {e.stderr}")
        if check:
            raise
        return e

def check_environment():
    """Check if required environment variables are set"""
    print("🔍 Checking environment variables...")
    
    required_vars = {
        "DATABASE_URL": "PostgreSQL connection string",
        "OPENAI_API_KEY": "OpenAI API key",
        "SECRET_KEY": "JWT secret key"
    }
    
    optional_vars = {
        "REDIS_URL": "Redis connection string (optional)",
        "GOOGLE_CLIENT_ID": "Google OAuth client ID (optional)",
        "GOOGLE_CLIENT_SECRET": "Google OAuth client secret (optional)"
    }
    
    missing_required = []
    for var, desc in required_vars.items():
        if not os.getenv(var):
            missing_required.append(f"  - {var}: {desc}")
    
    if missing_required:
        print("❌ Missing required environment variables:")
        for var in missing_required:
            print(var)
        return False
    
    print("✅ All required environment variables are set")
    
    # Check optional variables
    missing_optional = []
    for var, desc in optional_vars.items():
        if not os.getenv(var):
            missing_optional.append(f"  - {var}: {desc}")
    
    if missing_optional:
        print("⚠️  Optional environment variables not set:")
        for var in missing_optional:
            print(var)
    
    return True

def test_database_connection():
    """Test database connection"""
    print("🔍 Testing database connection...")
    try:
        from database.connection import engine
        with engine.connect() as conn:
            result = conn.execute("SELECT 1")
            print("✅ Database connection successful")
            return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def run_migrations():
    """Run Alembic database migrations"""
    print("🗄️  Running database migrations...")
    
    try:
        # Change to database directory where alembic.ini is located
        db_dir = backend_dir / "database"
        
        # Run alembic upgrade
        result = run_command("alembic upgrade head", cwd=db_dir)
        
        if result.returncode == 0:
            print("✅ Database migrations completed successfully")
            return True
        else:
            print("❌ Database migrations failed")
            return False
            
    except Exception as e:
        print(f"❌ Migration error: {e}")
        return False

def setup_pgvector_extension():
    """Set up pgvector extension if needed"""
    print("🔧 Setting up pgvector extension...")
    
    try:
        from database.connection import engine
        from sqlalchemy import text
        
        with engine.connect() as conn:
            # Check if extension exists
            result = conn.execute(text(
                "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
            ))
            
            if result.fetchone():
                print("✅ pgvector extension already exists")
                return True
            else:
                print("⚠️  pgvector extension not found")
                try:
                    conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                    conn.commit()
                    print("✅ pgvector extension created successfully")
                    return True
                except Exception as e:
                    print(f"⚠️  Could not create pgvector extension: {e}")
                    print("💡 This is okay - vector search will be disabled")
                    return True  # Don't fail deployment for this
                    
    except Exception as e:
        print(f"⚠️  Could not check pgvector extension: {e}")
        print("💡 This is okay - vector search will be disabled")
        return True  # Don't fail deployment for this

def test_redis_connection():
    """Test Redis connection"""
    print("🔍 Testing Redis connection...")
    
    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("⚠️  REDIS_URL not set - Redis features will be disabled")
        return True
    
    try:
        from common.utilities.redis_manager import redis_manager
        if redis_manager.is_available():
            print("✅ Redis connection successful")
            return True
        else:
            print("⚠️  Redis connection failed - Redis features will be disabled")
            return True  # Don't fail deployment for Redis
    except Exception as e:
        print(f"⚠️  Redis test failed: {e} - Redis features will be disabled")
        return True  # Don't fail deployment for Redis

def main():
    """Main deployment function"""
    print("🚀 Railway Deployment Setup")
    print("=" * 50)
    
    # Step 1: Check environment
    if not check_environment():
        print("❌ Environment check failed. Please set missing variables.")
        sys.exit(1)
    
    # Step 2: Test database connection
    if not test_database_connection():
        print("❌ Database connection failed. Check your DATABASE_URL.")
        sys.exit(1)
    
    # Step 3: Set up pgvector extension
    setup_pgvector_extension()
    
    # Step 4: Run migrations
    if not run_migrations():
        print("❌ Database migrations failed.")
        sys.exit(1)
    
    # Step 5: Test Redis (optional)
    test_redis_connection()
    
    print("🎉 Deployment setup completed successfully!")
    print("✅ Your app is ready to run on Railway!")

if __name__ == "__main__":
    main()
