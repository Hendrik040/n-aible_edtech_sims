"""rename_scenario_to_simulation

Revision ID: rename_scenario_to_sim
Revises: a4de75a977bc
Create Date: 2025-12-13 13:01:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'rename_scenario_to_sim'
down_revision: Union[str, None] = 'a4de75a977bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Rename all scenario-related tables and columns to simulation.
    
    Tables renamed:
    - scenarios → simulations
    - scenario_personas → simulation_personas
    - scenario_scenes → simulation_scenes
    - scenario_reviews → simulation_reviews
    
    Columns renamed:
    - scenario_id → simulation_id (in all tables)
    """
    
    # Step 1: Rename tables
    op.rename_table('scenarios', 'simulations')
    op.rename_table('scenario_personas', 'simulation_personas')
    op.rename_table('scenario_scenes', 'simulation_scenes')
    
    # Check if scenario_reviews table exists before renaming
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if 'scenario_reviews' in inspector.get_table_names():
        op.rename_table('scenario_reviews', 'simulation_reviews')
    
    # Step 2: Drop and recreate foreign key constraints with new table names
    # This must be done before renaming columns
    
    # Drop foreign keys that reference scenarios/scenario_personas/scenario_scenes
    # We'll recreate them after renaming columns
    
    # Step 3: Rename scenario_id columns to simulation_id
    # Start with tables that don't have self-referencing FKs
    
    # simulation_personas.scenario_id → simulation_id
    op.alter_column('simulation_personas', 'scenario_id',
                    new_column_name='simulation_id',
                    existing_type=sa.Integer(),
                    existing_nullable=False)
    
    # simulation_scenes.scenario_id → simulation_id
    op.alter_column('simulation_scenes', 'scenario_id',
                    new_column_name='simulation_id',
                    existing_type=sa.Integer(),
                    existing_nullable=False)
    
    # user_progress.scenario_id → simulation_id
    op.alter_column('user_progress', 'scenario_id',
                    new_column_name='simulation_id',
                    existing_type=sa.Integer(),
                    existing_nullable=False)
    
    # Check and rename in other tables if they exist
    if 'simulation_files' in inspector.get_table_names():
        op.alter_column('simulation_files', 'scenario_id',
                        new_column_name='simulation_id',
                        existing_type=sa.Integer(),
                        existing_nullable=True)
    
    if 'simulation_reviews' in inspector.get_table_names():
        op.alter_column('simulation_reviews', 'scenario_id',
                        new_column_name='simulation_id',
                        existing_type=sa.Integer(),
                        existing_nullable=True)
    
    if 'grading_materials' in inspector.get_table_names():
        # grading_materials already has simulation_id, but check if scenario_id exists
        columns = [col['name'] for col in inspector.get_columns('grading_materials')]
        if 'scenario_id' in columns:
            op.alter_column('grading_materials', 'scenario_id',
                            new_column_name='simulation_id',
                            existing_type=sa.Integer(),
                            existing_nullable=True)
    
    # Step 4: Update foreign key constraints to reference new table names
    # Drop old constraints and create new ones
    
    # simulation_personas foreign key
    op.drop_constraint('fk_scenario_personas_scenario_id_scenarios', 'simulation_personas', type_='foreignkey')
    op.create_foreign_key('fk_simulation_personas_simulation_id_simulations',
                          'simulation_personas', 'simulations',
                          ['simulation_id'], ['id'])
    
    # simulation_scenes foreign key
    op.drop_constraint('fk_scenario_scenes_scenario_id_scenarios', 'simulation_scenes', type_='foreignkey')
    op.create_foreign_key('fk_simulation_scenes_simulation_id_simulations',
                          'simulation_scenes', 'simulations',
                          ['simulation_id'], ['id'])
    
    # user_progress foreign key
    op.drop_constraint('fk_user_progress_scenario_id_scenarios', 'user_progress', type_='foreignkey')
    op.create_foreign_key('fk_user_progress_simulation_id_simulations',
                          'user_progress', 'simulations',
                          ['simulation_id'], ['id'])
    
    # user_progress.current_scene_id foreign key
    op.drop_constraint('fk_user_progress_current_scene_id_scenario_scenes', 'user_progress', type_='foreignkey')
    op.create_foreign_key('fk_user_progress_current_scene_id_simulation_scenes',
                          'user_progress', 'simulation_scenes',
                          ['current_scene_id'], ['id'])
    
    # simulations self-referencing foreign keys (published_version_id, draft_of_id)
    op.drop_constraint('fk_scenarios_published_version_id_scenarios', 'simulations', type_='foreignkey')
    op.drop_constraint('fk_scenarios_draft_of_id_scenarios', 'simulations', type_='foreignkey')
    op.create_foreign_key('fk_simulations_published_version_id_simulations',
                          'simulations', 'simulations',
                          ['published_version_id'], ['id'])
    op.create_foreign_key('fk_simulations_draft_of_id_simulations',
                          'simulations', 'simulations',
                          ['draft_of_id'], ['id'])
    
    # Update foreign keys in other tables
    if 'simulation_files' in inspector.get_table_names():
        op.drop_constraint('fk_simulation_files_scenario_id_scenarios', 'simulation_files', type_='foreignkey', checkfirst=True)
        op.create_foreign_key('fk_simulation_files_simulation_id_simulations',
                              'simulation_files', 'simulations',
                              ['simulation_id'], ['id'])
    
    if 'simulation_reviews' in inspector.get_table_names():
        op.drop_constraint('fk_scenario_reviews_scenario_id_scenarios', 'simulation_reviews', type_='foreignkey', checkfirst=True)
        op.create_foreign_key('fk_simulation_reviews_simulation_id_simulations',
                              'simulation_reviews', 'simulations',
                              ['simulation_id'], ['id'])
    
    # Update foreign keys in runtime tables
    # scene_personas junction table
    op.drop_constraint('scene_personas_scene_id_fkey', 'scene_personas', type_='foreignkey', checkfirst=True)
    op.drop_constraint('scene_personas_persona_id_fkey', 'scene_personas', type_='foreignkey', checkfirst=True)
    op.create_foreign_key('fk_scene_personas_scene_id_simulation_scenes',
                          'scene_personas', 'simulation_scenes',
                          ['scene_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_scene_personas_persona_id_simulation_personas',
                          'scene_personas', 'simulation_personas',
                          ['persona_id'], ['id'], ondelete='CASCADE')
    
    # scene_progress
    if 'scene_progress' in inspector.get_table_names():
        op.drop_constraint('fk_scene_progress_scene_id_scenario_scenes', 'scene_progress', type_='foreignkey', checkfirst=True)
        op.create_foreign_key('fk_scene_progress_scene_id_simulation_scenes',
                              'scene_progress', 'simulation_scenes',
                              ['scene_id'], ['id'])
    
    # conversation_logs
    if 'conversation_logs' in inspector.get_table_names():
        op.drop_constraint('fk_conversation_logs_scene_id_scenario_scenes', 'conversation_logs', type_='foreignkey', checkfirst=True)
        op.drop_constraint('fk_conversation_logs_persona_id_scenario_personas', 'conversation_logs', type_='foreignkey', checkfirst=True)
        op.create_foreign_key('fk_conversation_logs_scene_id_simulation_scenes',
                              'conversation_logs', 'simulation_scenes',
                              ['scene_id'], ['id'])
        op.create_foreign_key('fk_conversation_logs_persona_id_simulation_personas',
                              'conversation_logs', 'simulation_personas',
                              ['persona_id'], ['id'])
    
    # agent_sessions
    if 'agent_sessions' in inspector.get_table_names():
        op.drop_constraint('fk_agent_sessions_persona_id_scenario_personas', 'agent_sessions', type_='foreignkey', checkfirst=True)
        op.create_foreign_key('fk_agent_sessions_persona_id_simulation_personas',
                              'agent_sessions', 'simulation_personas',
                              ['persona_id'], ['id'])
    
    # session_memory
    if 'session_memory' in inspector.get_table_names():
        op.drop_constraint('fk_session_memory_scene_id_scenario_scenes', 'session_memory', type_='foreignkey', checkfirst=True)
        op.drop_constraint('fk_session_memory_related_persona_id_scenario_personas', 'session_memory', type_='foreignkey', checkfirst=True)
        op.create_foreign_key('fk_session_memory_scene_id_simulation_scenes',
                              'session_memory', 'simulation_scenes',
                              ['scene_id'], ['id'])
        op.create_foreign_key('fk_session_memory_related_persona_id_simulation_personas',
                              'session_memory', 'simulation_personas',
                              ['related_persona_id'], ['id'])
    
    # conversation_summaries
    if 'conversation_summaries' in inspector.get_table_names():
        op.drop_constraint('fk_conversation_summaries_scene_id_scenario_scenes', 'conversation_summaries', type_='foreignkey', checkfirst=True)
        op.create_foreign_key('fk_conversation_summaries_scene_id_simulation_scenes',
                              'conversation_summaries', 'simulation_scenes',
                              ['scene_id'], ['id'])
    
    # grading_materials
    if 'grading_materials' in inspector.get_table_names():
        op.drop_constraint('fk_grading_materials_simulation_id_scenarios', 'grading_materials', type_='foreignkey', checkfirst=True)
        op.create_foreign_key('fk_grading_materials_simulation_id_simulations',
                              'grading_materials', 'simulations',
                              ['simulation_id'], ['id'])
    
    # Step 5: Update indexes
    # Rename indexes that reference old table/column names
    op.execute("DROP INDEX IF EXISTS ix_scenarios_id")
    op.execute("DROP INDEX IF EXISTS ix_scenarios_unique_id")
    op.create_index('ix_simulations_id', 'simulations', ['id'], unique=False)
    op.create_index('ix_simulations_unique_id', 'simulations', ['unique_id'], unique=True)
    
    op.execute("DROP INDEX IF EXISTS ix_scenario_personas_id")
    op.execute("DROP INDEX IF EXISTS ix_scenario_personas_scenario_id")
    op.create_index('ix_simulation_personas_id', 'simulation_personas', ['id'], unique=False)
    op.create_index('ix_simulation_personas_simulation_id', 'simulation_personas', ['simulation_id'], unique=False)
    
    op.execute("DROP INDEX IF EXISTS ix_scenario_scenes_id")
    op.execute("DROP INDEX IF EXISTS ix_scenario_scenes_scenario_id")
    op.create_index('ix_simulation_scenes_id', 'simulation_scenes', ['id'], unique=False)
    op.create_index('ix_simulation_scenes_simulation_id', 'simulation_scenes', ['simulation_id'], unique=False)
    
    op.execute("DROP INDEX IF EXISTS ix_user_progress_scenario_id")
    op.create_index('ix_user_progress_simulation_id', 'user_progress', ['simulation_id'], unique=False)


def downgrade() -> None:
    """
    Reverse the migration: rename simulation back to scenario.
    """
    
    # Step 1: Drop new foreign keys and recreate old ones
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Drop new foreign keys
    op.drop_constraint('fk_simulation_personas_simulation_id_simulations', 'simulation_personas', type_='foreignkey', checkfirst=True)
    op.drop_constraint('fk_simulation_scenes_simulation_id_simulations', 'simulation_scenes', type_='foreignkey', checkfirst=True)
    op.drop_constraint('fk_user_progress_simulation_id_simulations', 'user_progress', type_='foreignkey', checkfirst=True)
    op.drop_constraint('fk_user_progress_current_scene_id_simulation_scenes', 'user_progress', type_='foreignkey', checkfirst=True)
    op.drop_constraint('fk_simulations_published_version_id_simulations', 'simulations', type_='foreignkey', checkfirst=True)
    op.drop_constraint('fk_simulations_draft_of_id_simulations', 'simulations', type_='foreignkey', checkfirst=True)
    
    # Recreate old foreign keys
    op.create_foreign_key('fk_scenario_personas_scenario_id_scenarios',
                          'simulation_personas', 'scenarios',
                          ['simulation_id'], ['id'])
    op.create_foreign_key('fk_scenario_scenes_scenario_id_scenarios',
                          'simulation_scenes', 'scenarios',
                          ['simulation_id'], ['id'])
    op.create_foreign_key('fk_user_progress_scenario_id_scenarios',
                          'user_progress', 'scenarios',
                          ['simulation_id'], ['id'])
    op.create_foreign_key('fk_user_progress_current_scene_id_scenario_scenes',
                          'user_progress', 'scenario_scenes',
                          ['current_scene_id'], ['id'])
    op.create_foreign_key('fk_scenarios_published_version_id_scenarios',
                          'simulations', 'scenarios',
                          ['published_version_id'], ['id'])
    op.create_foreign_key('fk_scenarios_draft_of_id_scenarios',
                          'simulations', 'scenarios',
                          ['draft_of_id'], ['id'])
    
    # Step 2: Rename columns back
    op.alter_column('simulation_personas', 'simulation_id',
                    new_column_name='scenario_id',
                    existing_type=sa.Integer(),
                    existing_nullable=False)
    op.alter_column('simulation_scenes', 'simulation_id',
                    new_column_name='scenario_id',
                    existing_type=sa.Integer(),
                    existing_nullable=False)
    op.alter_column('user_progress', 'simulation_id',
                    new_column_name='scenario_id',
                    existing_type=sa.Integer(),
                    existing_nullable=False)
    
    # Step 3: Rename tables back
    op.rename_table('simulations', 'scenarios')
    op.rename_table('simulation_personas', 'scenario_personas')
    op.rename_table('simulation_scenes', 'scenario_scenes')
    
    if 'simulation_reviews' in inspector.get_table_names():
        op.rename_table('simulation_reviews', 'scenario_reviews')
    
    # Step 4: Recreate old indexes
    op.execute("DROP INDEX IF EXISTS ix_simulations_id")
    op.execute("DROP INDEX IF EXISTS ix_simulations_unique_id")
    op.create_index('ix_scenarios_id', 'scenarios', ['id'], unique=False)
    op.create_index('ix_scenarios_unique_id', 'scenarios', ['unique_id'], unique=True)
    
    op.execute("DROP INDEX IF EXISTS ix_simulation_personas_id")
    op.execute("DROP INDEX IF EXISTS ix_simulation_personas_simulation_id")
    op.create_index('ix_scenario_personas_id', 'scenario_personas', ['id'], unique=False)
    op.create_index('ix_scenario_personas_scenario_id', 'scenario_personas', ['scenario_id'], unique=False)
    
    op.execute("DROP INDEX IF EXISTS ix_simulation_scenes_id")
    op.execute("DROP INDEX IF EXISTS ix_simulation_scenes_simulation_id")
    op.create_index('ix_scenario_scenes_id', 'scenario_scenes', ['id'], unique=False)
    op.create_index('ix_scenario_scenes_scenario_id', 'scenario_scenes', ['scenario_id'], unique=False)
    
    op.execute("DROP INDEX IF EXISTS ix_user_progress_simulation_id")
    op.create_index('ix_user_progress_scenario_id', 'user_progress', ['scenario_id'], unique=False)
