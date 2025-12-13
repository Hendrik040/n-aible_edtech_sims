"""create_simulation_runtime_tables

Revision ID: 14eb31ccda01
Revises: 1b984a286074
Create Date: 2025-12-12 20:38:12.779214

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '14eb31ccda01'
down_revision: Union[str, None] = '1b984a286074'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Create simulation runtime tables using raw SQL with IF NOT EXISTS
    to handle cases where tables may already exist from other migrations.
    
    Tables that may conflict with cohort migration (7099884d5945):
    - scenario_reviews (skip - created by cohorts)
    - student_simulation_instances (skip - created by cohorts with full schema)
    """
    conn = op.get_bind()
    
    # vector_embeddings
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS vector_embeddings (
            id SERIAL PRIMARY KEY,
            entity_type VARCHAR NOT NULL,
            entity_id INTEGER NOT NULL,
            embedding_vector JSON,
            embedding_model VARCHAR,
            embedding_metadata JSON,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_vector_embeddings_entity_id ON vector_embeddings(entity_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_vector_embeddings_id ON vector_embeddings(id)"))
    
    # grading_materials
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS grading_materials (
            id SERIAL PRIMARY KEY,
            simulation_id INTEGER NOT NULL REFERENCES scenarios(id),
            filename VARCHAR NOT NULL,
            content TEXT,
            processing_status VARCHAR NOT NULL,
            processing_log JSON,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_grading_materials_id ON grading_materials(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_grading_materials_simulation_id ON grading_materials(simulation_id)"))
    
    # grading_material_chunks (depends on grading_materials)
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS grading_material_chunks (
            id SERIAL PRIMARY KEY,
            material_id INTEGER NOT NULL REFERENCES grading_materials(id),
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding_vector JSON,
            embedding_model VARCHAR,
            embedding_dimension INTEGER,
            content_hash VARCHAR,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_grading_material_chunks_content_hash ON grading_material_chunks(content_hash)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_grading_material_chunks_id ON grading_material_chunks(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_grading_material_chunks_material_id ON grading_material_chunks(material_id)"))
    
    # user_progress - core simulation runtime table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS user_progress (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            scenario_id INTEGER NOT NULL REFERENCES scenarios(id),
            current_scene_id INTEGER NOT NULL REFERENCES scenario_scenes(id),
            simulation_status VARCHAR NOT NULL,
            orchestrator_data JSON,
            scenes_completed INTEGER DEFAULT 0,
            session_count INTEGER DEFAULT 0,
            total_attempts INTEGER DEFAULT 0,
            hints_used INTEGER DEFAULT 0,
            forced_progressions INTEGER DEFAULT 0,
            completion_percentage FLOAT DEFAULT 0.0,
            total_time_spent INTEGER DEFAULT 0,
            final_score FLOAT,
            started_at TIMESTAMP WITH TIME ZONE,
            completed_at TIMESTAMP WITH TIME ZONE,
            last_activity TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_progress_id ON user_progress(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_progress_scenario_id ON user_progress(scenario_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_user_progress_user_id ON user_progress(user_id)"))
    
    # agent_sessions (depends on user_progress)
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS agent_sessions (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR NOT NULL,
            user_progress_id INTEGER NOT NULL REFERENCES user_progress(id),
            persona_id INTEGER REFERENCES scenario_personas(id),
            agent_type VARCHAR NOT NULL,
            agent_id VARCHAR,
            session_type VARCHAR,
            session_config JSON,
            session_state JSON,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
            expires_at TIMESTAMP WITH TIME ZONE,
            last_accessed_at TIMESTAMP WITH TIME ZONE,
            last_activity TIMESTAMP WITH TIME ZONE
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_agent_sessions_id ON agent_sessions(id)"))
    conn.execute(sa.text("CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_sessions_session_id ON agent_sessions(session_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_agent_sessions_user_progress_id ON agent_sessions(user_progress_id)"))
    
    # conversation_logs (depends on user_progress)
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS conversation_logs (
            id SERIAL PRIMARY KEY,
            user_progress_id INTEGER NOT NULL REFERENCES user_progress(id),
            scene_id INTEGER NOT NULL REFERENCES scenario_scenes(id),
            persona_id INTEGER REFERENCES scenario_personas(id),
            message_type VARCHAR NOT NULL,
            sender_name VARCHAR NOT NULL,
            message_content TEXT NOT NULL,
            message_order INTEGER NOT NULL,
            timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
            ai_model_version VARCHAR,
            processing_time FLOAT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_conversation_logs_id ON conversation_logs(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_conversation_logs_message_order ON conversation_logs(message_order)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_conversation_logs_scene_id ON conversation_logs(scene_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_conversation_logs_user_progress_id ON conversation_logs(user_progress_id)"))
    
    # conversation_summaries (depends on user_progress)
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS conversation_summaries (
            id SERIAL PRIMARY KEY,
            user_progress_id INTEGER NOT NULL REFERENCES user_progress(id),
            scene_id INTEGER REFERENCES scenario_scenes(id),
            summary_type VARCHAR NOT NULL,
            summary_text TEXT NOT NULL,
            key_points JSON,
            learning_moments JSON,
            insights JSON,
            recommendations JSON,
            summary_metadata JSON,
            quality_score FLOAT NOT NULL DEFAULT 0.0,
            relevance_score FLOAT NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_conversation_summaries_id ON conversation_summaries(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_conversation_summaries_user_progress_id ON conversation_summaries(user_progress_id)"))
    
    # scene_progress (depends on user_progress)
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS scene_progress (
            id SERIAL PRIMARY KEY,
            user_progress_id INTEGER NOT NULL REFERENCES user_progress(id),
            scene_id INTEGER NOT NULL REFERENCES scenario_scenes(id),
            status VARCHAR NOT NULL,
            progress_data JSON,
            completed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_scene_progress_id ON scene_progress(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_scene_progress_scene_id ON scene_progress(scene_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_scene_progress_user_progress_id ON scene_progress(user_progress_id)"))
    
    # session_memory (depends on user_progress)
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS session_memory (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR NOT NULL,
            memory_type VARCHAR NOT NULL,
            memory_content TEXT NOT NULL,
            user_progress_id INTEGER NOT NULL REFERENCES user_progress(id),
            scene_id INTEGER REFERENCES scenario_scenes(id),
            related_persona_id INTEGER REFERENCES scenario_personas(id),
            importance_score FLOAT NOT NULL DEFAULT 0.0,
            memory_metadata JSON,
            access_count INTEGER NOT NULL DEFAULT 0,
            last_accessed TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
        )
    """))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_session_memory_id ON session_memory(id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_session_memory_session_id ON session_memory(session_id)"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_session_memory_user_progress_id ON session_memory(user_progress_id)"))
    
    # NOTE: scenario_reviews and student_simulation_instances are SKIPPED
    # They are already created by the cohort migration (7099884d5945)
    
    # NOTE: User column alterations are SKIPPED
    # They are already applied by the cohort migration (7099884d5945)


def downgrade() -> None:
    """Drop simulation runtime tables in reverse order."""
    conn = op.get_bind()
    
    # Drop in reverse dependency order
    conn.execute(sa.text("DROP TABLE IF EXISTS session_memory CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS scene_progress CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS conversation_summaries CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS conversation_logs CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS agent_sessions CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS user_progress CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS grading_material_chunks CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS grading_materials CASCADE"))
    conn.execute(sa.text("DROP TABLE IF EXISTS vector_embeddings CASCADE"))
