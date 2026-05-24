"""add_cascade_delete_to_user_progress_fks

Revision ID: add_cascade_delete_user_progress
Revises: 8e1341effc06
Create Date: 2025-12-18 03:54:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_cascade_delete_user_progress'
down_revision: Union[str, None] = '8e1341effc06'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add ON DELETE CASCADE to foreign keys referencing user_progress.id.
    
    This ensures that when user_progress is deleted, all related records
    (agent_sessions, session_memory, conversation_logs, conversation_summaries,
    scene_progress, student_simulation_instances) are automatically deleted,
    preventing FK violations and race conditions.
    """
    conn = op.get_bind()
    
    # Drop existing foreign keys and recreate with CASCADE
    tables_to_update = [
        ('agent_sessions', 'agent_sessions_user_progress_id_fkey'),
        ('session_memory', 'session_memory_user_progress_id_fkey'),
        ('conversation_logs', 'conversation_logs_user_progress_id_fkey'),
        ('conversation_summaries', 'conversation_summaries_user_progress_id_fkey'),
        ('scene_progress', 'scene_progress_user_progress_id_fkey'),
        ('student_simulation_instances', 'fk_student_sim_instances_user_progress'),
    ]
    
    for table_name, fk_name in tables_to_update:
        try:
            # Drop existing FK constraint
            conn.execute(sa.text(f"""
                ALTER TABLE {table_name} 
                DROP CONSTRAINT IF EXISTS {fk_name}
            """))
            
            # Recreate with ON DELETE CASCADE
            conn.execute(sa.text(f"""
                ALTER TABLE {table_name}
                ADD CONSTRAINT {fk_name}
                FOREIGN KEY (user_progress_id)
                REFERENCES user_progress(id)
                ON DELETE CASCADE
            """))
        except Exception as e:
            # If constraint doesn't exist or has different name, try to find it
            # and recreate with CASCADE
            inspector = sa.inspect(conn)
            fks = inspector.get_foreign_keys(table_name)
            for fk in fks:
                if 'user_progress_id' in fk.get('constrained_columns', []):
                    old_name = fk.get('name')
                    if old_name:
                        try:
                            conn.execute(sa.text(f"""
                                ALTER TABLE {table_name}
                                DROP CONSTRAINT IF EXISTS {old_name}
                            """))
                        except:
                            pass
                    
                    # Recreate with CASCADE
                    conn.execute(sa.text(f"""
                        ALTER TABLE {table_name}
                        ADD CONSTRAINT {fk_name}
                        FOREIGN KEY (user_progress_id)
                        REFERENCES user_progress(id)
                        ON DELETE CASCADE
                    """))
                    break


def downgrade() -> None:
    """
    Remove ON DELETE CASCADE from foreign keys (revert to RESTRICT).
    Note: This will fail if there are orphaned records.
    """
    conn = op.get_bind()
    
    tables_to_update = [
        ('agent_sessions', 'agent_sessions_user_progress_id_fkey'),
        ('session_memory', 'session_memory_user_progress_id_fkey'),
        ('conversation_logs', 'conversation_logs_user_progress_id_fkey'),
        ('conversation_summaries', 'conversation_summaries_user_progress_id_fkey'),
        ('scene_progress', 'scene_progress_user_progress_id_fkey'),
        ('student_simulation_instances', 'fk_student_sim_instances_user_progress'),
    ]
    
    for table_name, fk_name in tables_to_update:
        try:
            # Drop CASCADE constraint
            conn.execute(sa.text(f"""
                ALTER TABLE {table_name}
                DROP CONSTRAINT IF EXISTS {fk_name}
            """))
            
            # Recreate without CASCADE (default is RESTRICT)
            conn.execute(sa.text(f"""
                ALTER TABLE {table_name}
                ADD CONSTRAINT {fk_name}
                FOREIGN KEY (user_progress_id)
                REFERENCES user_progress(id)
            """))
        except Exception as e:
            # If constraint doesn't exist, skip
            pass
