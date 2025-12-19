#!/usr/bin/env python3
"""
Fix missing progress_data column in scene_progress table.

This script checks if the progress_data column exists in the scene_progress table
and adds it if it's missing. This is a safety script to handle cases where
migrations haven't been run or the database schema is out of sync.
"""

import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from common.db.core import SessionLocal
from common.config import get_settings

settings = get_settings()


def check_and_fix_progress_data_column():
    """Check if progress_data column exists and add it if missing."""
    db = SessionLocal()
    try:
        # Check if column exists
        result = db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'scene_progress' 
            AND column_name = 'progress_data'
        """))
        
        column_exists = result.first() is not None
        
        if column_exists:
            print("✓ progress_data column already exists in scene_progress table")
            return True
        
        print("✗ progress_data column is missing in scene_progress table")
        print("  Adding progress_data column...")
        
        # Add the column
        db.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name = 'scene_progress' AND column_name = 'progress_data'
                ) THEN
                    ALTER TABLE scene_progress ADD COLUMN progress_data JSON;
                END IF;
            END $$;
        """))
        
        db.commit()
        print("✓ Successfully added progress_data column to scene_progress table")
        return True
        
    except Exception as e:
        db.rollback()
        print(f"✗ Error fixing schema: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


def verify_schema():
    """Verify the scene_progress table schema matches expectations."""
    db = SessionLocal()
    try:
        # Get all columns in scene_progress table
        result = db.execute(text("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns 
            WHERE table_name = 'scene_progress'
            ORDER BY ordinal_position
        """))
        
        columns = result.fetchall()
        
        print("\nCurrent scene_progress table schema:")
        print("-" * 60)
        for col_name, data_type, is_nullable in columns:
            nullable_str = "NULL" if is_nullable == "YES" else "NOT NULL"
            print(f"  {col_name:25} {data_type:15} {nullable_str}")
        print("-" * 60)
        
        # Check for required columns
        required_columns = {
            'id', 'user_progress_id', 'scene_id', 'status', 
            'progress_data', 'completed_at', 'created_at', 'updated_at'
        }
        
        existing_columns = {col[0] for col in columns}
        missing_columns = required_columns - existing_columns
        
        if missing_columns:
            print(f"\n⚠ Missing required columns: {', '.join(missing_columns)}")
            return False
        else:
            print("\n✓ All required columns are present")
            return True
            
    except Exception as e:
        print(f"✗ Error verifying schema: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Scene Progress Schema Fix Script")
    print("=" * 60)
    print(f"Database: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'N/A'}")
    print()
    
    # Verify current schema
    schema_ok = verify_schema()
    print()
    
    # Fix if needed
    if not schema_ok:
        print("Attempting to fix schema...")
        print()
        success = check_and_fix_progress_data_column()
        
        if success:
            print()
            print("Verifying fix...")
            verify_schema()
        else:
            print("\n✗ Failed to fix schema. Please run migrations manually:")
            print("  cd backend && alembic upgrade head")
            sys.exit(1)
    else:
        print("Schema is correct. No fixes needed.")
    
    print()
    print("=" * 60)
    print("Done")
    print("=" * 60)
