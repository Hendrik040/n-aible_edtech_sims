#!/usr/bin/env python3
"""
Database Clearing Script
This script safely clears all data from the database by dropping and recreating tables
"""

import os
import sys
import logging
from pathlib import Path
from sqlalchemy import create_engine, text, MetaData, Table
from sqlalchemy.schema import DropTable
from sqlalchemy.exc import SQLAlchemyError
from alembic.config import Config
from alembic import command

# Add the backend directory to the Python path
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# Import database connection and models
from database.connection import engine, Base, settings
from database.models import *

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def apply_migrations(db_url: str) -> None:
    """Apply Alembic migrations to recreate the database schema"""
    alembic_ini = Path(__file__).parent / "database" / "alembic.ini"
    cfg = Config(str(alembic_ini))
    cfg.set_main_option("sqlalchemy.url", db_url)
    
    # Set the correct working directory for migrations
    # The alembic.ini has script_location = migrations, so we need to be in the database directory
    original_cwd = os.getcwd()
    database_dir = Path(__file__).parent / "database"
    os.chdir(database_dir)
    
    try:
        command.upgrade(cfg, "head")
    finally:
        # Restore original working directory
        os.chdir(original_cwd)

def clear_database():
    """Clear all data from the database by dropping and recreating tables"""
    logger.info("🗑️  Starting database clearing process...")
    
    try:
        # Test connection first
        logger.info("Testing database connection...")
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful")
        
        # Get database URL for logging (partial for security)
        from urllib.parse import urlparse
        parsed = urlparse(settings.database_url)
        db_url_partial = f"{parsed.scheme}://***@{parsed.hostname or 'localhost'}/{parsed.path.lstrip('/')}"
        logger.info(f"🔗 Database URL: {db_url_partial}")
        
        # Confirm with user
        print("\n" + "="*60)
        print("⚠️  WARNING: This will DELETE ALL DATA in the database!")
        print("="*60)
        from common.utils.secure_logging import secure_print_database_url
        secure_print_database_url(settings.database_url)
        print("This action cannot be undone!")
        print("="*60)
        
        response = input("\nAre you sure you want to clear the database? (yes/no): ").strip().lower()
        if response not in ['yes', 'y']:
            logger.info("❌ Database clearing cancelled by user")
            return False
        
        # Drop all tables
        logger.info("Dropping all tables...")
        with engine.connect() as conn:
            # Start a transaction
            trans = conn.begin()
            try:
                # Drop all tables in the correct order (respecting foreign key constraints)
                logger.info("Dropping tables in dependency order...")
                
                # Reflect all tables and get them in reverse dependency order
                metadata = MetaData()
                metadata.reflect(bind=engine)
                tables = list(metadata.tables.values())
                
                logger.info(f"Found {len(tables)} tables to drop: {', '.join(table.name for table in tables)}")
                
                # Drop all tables in reverse dependency order using SQLAlchemy DropTable
                # This ensures proper quoting and dependency handling
                for table in reversed(metadata.sorted_tables):
                    logger.info(f"Dropping table: {table.name}")
                    # Use SQLAlchemy DropTable for proper identifier quoting
                    drop_stmt = DropTable(table)
                    
                    # For PostgreSQL, add CASCADE to handle foreign key constraints
                    if engine.dialect.name == 'postgresql':
                        # Compile the statement and add CASCADE
                        compiled_stmt = drop_stmt.compile(bind=engine)
                        sql_str = str(compiled_stmt) + " CASCADE"
                        conn.execute(text(sql_str))
                    else:
                        # For other databases, use the standard compiled statement
                        compiled_stmt = drop_stmt.compile(bind=engine)
                        conn.execute(compiled_stmt)
                
                # Commit the transaction
                trans.commit()
                logger.info("✅ All tables dropped successfully")
                
            except Exception as e:
                trans.rollback()
                logger.error(f"❌ Error dropping tables: {e}")
                raise
        
        # Recreate schema via Alembic to ensure extensions/indexes/etc. are applied
        logger.info("Recreating all tables via Alembic migrations...")
        apply_migrations(settings.database_url)
        logger.info("✅ All migrations applied successfully")
        
        # Verify tables were created
        with engine.connect() as conn:
            dialect_name = engine.dialect.name
            if dialect_name == 'postgresql':
                result = conn.execute(text("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                """))
                tables = [row[0] for row in result.fetchall()]
            elif dialect_name == 'sqlite':
                result = conn.execute(text("""
                    SELECT name 
                    FROM sqlite_master 
                    WHERE type = 'table' 
                    AND name NOT LIKE 'sqlite_%'
                    ORDER BY name
                """))
                tables = [row[0] for row in result.fetchall()]
            else:
                # Fallback to SQLAlchemy Inspector
                from sqlalchemy import inspect
                inspector = inspect(engine)
                tables = inspector.get_table_names()
            
            logger.info(f"✅ Verified {len(tables)} tables created: {', '.join(tables)}")
        
        logger.info("\n" + "="*60)
        logger.info("🎉 Database cleared successfully!")
        logger.info("All tables have been dropped and recreated.")
        logger.info("The database is now empty and ready for fresh data.")
        logger.info("="*60)
        
        return True
        
    except SQLAlchemyError as e:
        logger.error(f"❌ Database error: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        return False

def main():
    """Main function"""
    logger.info("🚀 Database Clearing Script")
    logger.info("="*50)
    
    if clear_database():
        logger.info("✅ Database clearing completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Database clearing failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
