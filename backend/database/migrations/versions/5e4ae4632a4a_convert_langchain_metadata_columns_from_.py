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
    # Convert LangChain embedding metadata from JSON to JSONB
    op.execute("""
        ALTER TABLE langchain_pg_embedding 
        ALTER COLUMN cmetadata TYPE jsonb USING cmetadata::jsonb
    """)
    
    # Convert LangChain collection metadata from JSON to JSONB
    op.execute("""
        ALTER TABLE langchain_pg_collection 
        ALTER COLUMN cmetadata TYPE jsonb USING cmetadata::jsonb
    """)


def downgrade() -> None:
    # Convert back from JSONB to JSON
    op.execute("""
        ALTER TABLE langchain_pg_embedding 
        ALTER COLUMN cmetadata TYPE json USING cmetadata::json
    """)
    
    op.execute("""
        ALTER TABLE langchain_pg_collection 
        ALTER COLUMN cmetadata TYPE json USING cmetadata::json
    """)
