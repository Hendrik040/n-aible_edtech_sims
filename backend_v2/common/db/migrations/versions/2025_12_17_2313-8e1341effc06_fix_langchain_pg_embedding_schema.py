"""fix_langchain_pg_embedding_schema

Revision ID: 8e1341effc06
Revises: f107533b5a88
Create Date: 2025-12-17 23:13:20.669282

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e1341effc06'
down_revision: Union[str, None] = 'f107533b5a88'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fix langchain_pg_embedding table schema to match LangChain PGVector expectations.
    
    LangChain's PGVector expects the table to have an 'id' column (UUID).
    If the table exists without this column, we need to add it or recreate the table.
    """
    conn = op.get_bind()
    
    # Ensure pgvector extension is enabled
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    
    # Check if langchain_pg_embedding table exists
    result = conn.execute(sa.text("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'langchain_pg_embedding'
        )
    """))
    table_exists = result.scalar()
    
    if table_exists:
        # Check if 'id' column exists
        result = conn.execute(sa.text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'langchain_pg_embedding' AND column_name = 'id'
        """))
        id_column_exists = result.fetchone() is not None
        
        if not id_column_exists:
            # Check what columns the table currently has
            result = conn.execute(sa.text("""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = 'langchain_pg_embedding'
                ORDER BY ordinal_position
            """))
            columns = result.fetchall()
            
            # If table has no data or minimal structure, drop and let PGVector recreate
            # Otherwise, add the id column
            result = conn.execute(sa.text("""
                SELECT COUNT(*) FROM langchain_pg_embedding
            """))
            row_count = result.scalar()
            
            if row_count == 0:
                # Safe to drop and recreate - PGVector will create it with correct schema
                conn.execute(sa.text("DROP TABLE IF EXISTS langchain_pg_embedding CASCADE"))
                # Also drop the collection table if it exists (PGVector will recreate both)
                conn.execute(sa.text("DROP TABLE IF EXISTS langchain_pg_collection CASCADE"))
            else:
                # Table has data - add id column as UUID with default
                # Try to use gen_random_uuid() (PostgreSQL 13+), fallback to uuid_generate_v4()
                try:
                    # Check if gen_random_uuid() is available (PostgreSQL 13+)
                    conn.execute(sa.text("SELECT gen_random_uuid()"))
                    uuid_func = "gen_random_uuid()"
                except Exception:
                    # Fallback to uuid-ossp extension
                    try:
                        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\""))
                        uuid_func = "uuid_generate_v4()"
                    except Exception:
                        # If neither works, we'll need to handle this differently
                        uuid_func = None
                
                if uuid_func:
                    # Add id column as UUID with default
                    conn.execute(sa.text(f"""
                        ALTER TABLE langchain_pg_embedding 
                        ADD COLUMN IF NOT EXISTS id UUID DEFAULT {uuid_func}
                    """))
                    
                    # Update existing rows to have unique UUIDs
                    conn.execute(sa.text(f"""
                        UPDATE langchain_pg_embedding 
                        SET id = {uuid_func} 
                        WHERE id IS NULL
                    """))
                else:
                    # Last resort: add column without default and populate manually
                    conn.execute(sa.text("""
                        ALTER TABLE langchain_pg_embedding 
                        ADD COLUMN IF NOT EXISTS id UUID
                    """))
                    # This will require manual intervention if there are existing rows
                
                # Make id NOT NULL and add primary key constraint if it doesn't exist
                conn.execute(sa.text("""
                    ALTER TABLE langchain_pg_embedding 
                    ALTER COLUMN id SET NOT NULL
                """))
                
                # Check if primary key exists
                result = conn.execute(sa.text("""
                    SELECT constraint_name 
                    FROM information_schema.table_constraints 
                    WHERE table_name = 'langchain_pg_embedding' 
                    AND constraint_type = 'PRIMARY KEY'
                """))
                pk_exists = result.fetchone() is not None
                
                if not pk_exists:
                    # Add primary key constraint
                    conn.execute(sa.text("""
                        ALTER TABLE langchain_pg_embedding 
                        ADD PRIMARY KEY (id)
                    """))
    else:
        # Table doesn't exist - PGVector will create it when first used
        # Just ensure extensions are enabled
        pass


def downgrade() -> None:
    """
    This migration is mostly additive (adding id column).
    Downgrade would require knowing the previous state, which is complex.
    For safety, we'll leave the table as-is during downgrade.
    """
    pass

