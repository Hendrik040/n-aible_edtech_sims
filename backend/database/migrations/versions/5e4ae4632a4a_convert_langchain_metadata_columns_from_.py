"""Convert LangChain metadata columns from JSON to JSONB

Revision ID: 5e4ae4632a4a
Revises: 0a5eb83e9af2
Create Date: 2025-10-22 12:19:48.373215

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '5e4ae4632a4a'
down_revision = '0a5eb83e9af2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Check if LangChain tables exist before trying to alter them
    connection = op.get_bind()
    
    # Check if langchain_pg_embedding table exists
    embedding_exists = connection.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'langchain_pg_embedding')"
    ).scalar()
    
    if embedding_exists:
        # Convert LangChain embedding metadata from JSON to JSONB
        op.execute("""
            ALTER TABLE langchain_pg_embedding 
            ALTER COLUMN cmetadata TYPE jsonb USING cmetadata::jsonb
        """)
    
    # Check if langchain_pg_collection table exists
    collection_exists = connection.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'langchain_pg_collection')"
    ).scalar()
    
    if collection_exists:
        # Convert LangChain collection metadata from JSON to JSONB
        op.execute("""
            ALTER TABLE langchain_pg_collection 
            ALTER COLUMN cmetadata TYPE jsonb USING cmetadata::jsonb
        """)


def downgrade() -> None:
    # Check if LangChain tables exist before trying to alter them
    connection = op.get_bind()
    
    # Check if langchain_pg_embedding table exists
    embedding_exists = connection.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'langchain_pg_embedding')"
    ).scalar()
    
    if embedding_exists:
        # Convert back from JSONB to JSON
        op.execute("""
            ALTER TABLE langchain_pg_embedding 
            ALTER COLUMN cmetadata TYPE json USING cmetadata::json
        """)
    
    # Check if langchain_pg_collection table exists
    collection_exists = connection.execute(
        "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'langchain_pg_collection')"
    ).scalar()
    
    if collection_exists:
        # Convert back from JSONB to JSON
        op.execute("""
            ALTER TABLE langchain_pg_collection 
            ALTER COLUMN cmetadata TYPE json USING cmetadata::json
        """)
