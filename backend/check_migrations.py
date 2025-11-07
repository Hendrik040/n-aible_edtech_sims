#!/usr/bin/env python3
"""
Script to check database migration status and manually run migrations if needed.
This is useful for debugging migration issues on Railway.
"""
import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

from database.connection import engine, settings
from sqlalchemy import inspect, text
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from alembic.runtime.migration import MigrationContext

def check_column_exists(table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def get_current_revision():
    """Get the current database revision"""
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        current_rev = context.get_current_revision()
        return current_rev

def get_head_revision():
    """Get the head revision from migration files"""
    alembic_cfg = Config(str(backend_dir / "database" / "alembic.ini"))
    script = ScriptDirectory.from_config(alembic_cfg)
    head_rev = script.get_current_head()
    return head_rev

def run_migrations():
    """Run database migrations"""
    print("🔄 Running database migrations...")
    alembic_cfg = Config(str(backend_dir / "database" / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(backend_dir / "database" / "migrations"))
    
    try:
        command.upgrade(alembic_cfg, "head")
        print("✅ Migrations completed successfully")
        return True
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🔍 Checking database migration status...")
    print(f"Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'local'}")
    print()
    
    # Check if case_study_url column exists
    print("📊 Checking database schema...")
    if check_column_exists('scenarios', 'case_study_url'):
        print("✅ Column 'case_study_url' exists in scenarios table")
    else:
        print("❌ Column 'case_study_url' MISSING in scenarios table")
        print("   This column is required for the application to work correctly")
    
    print()
    
    # Check migration status
    print("📋 Checking migration status...")
    try:
        current_rev = get_current_revision()
        head_rev = get_head_revision()
        
        print(f"Current database revision: {current_rev or 'None (fresh database)'}")
        print(f"Head migration revision: {head_rev}")
        
        if current_rev == head_rev:
            print("✅ Database is up to date")
        else:
            print("⚠️  Database is not up to date - migrations need to be run")
            print()
            response = input("Would you like to run migrations now? (y/n): ")
            if response.lower() == 'y':
                if run_migrations():
                    # Check again
                    if check_column_exists('scenarios', 'case_study_url'):
                        print("✅ Column 'case_study_url' now exists after migration")
                    else:
                        print("❌ Column 'case_study_url' still missing after migration")
                        print("   You may need to manually add it or check migration files")
    except Exception as e:
        print(f"❌ Error checking migration status: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("Attempting to run migrations anyway...")
        response = input("Would you like to run migrations now? (y/n): ")
        if response.lower() == 'y':
            run_migrations()

if __name__ == "__main__":
    main()

