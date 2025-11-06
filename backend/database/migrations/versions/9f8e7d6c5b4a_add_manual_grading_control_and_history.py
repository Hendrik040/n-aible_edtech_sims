"""add_manual_grading_control_and_history

Revision ID: 9f8e7d6c5b4a
Revises: ce3d1a2246a0
Create Date: 2025-01-27 15:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '9f8e7d6c5b4a'
down_revision = 'ce3d1a2246a0'
branch_labels = None
depends_on = None


def upgrade() -> None:
    from sqlalchemy import inspect
    from sqlalchemy.exc import ProgrammingError
    
    # Get connection to check existing tables/columns
    connection = op.get_bind()
    inspector = inspect(connection)
    
    # Check which columns already exist in student_simulation_instances
    existing_columns = [col['name'] for col in inspector.get_columns('student_simulation_instances')]
    
    # Add AI grading fields to student_simulation_instances if they don't exist
    if 'ai_grade' not in existing_columns:
        op.add_column('student_simulation_instances', 
                      sa.Column('ai_grade', sa.Float(), nullable=True))
    
    if 'ai_feedback' not in existing_columns:
        op.add_column('student_simulation_instances', 
                      sa.Column('ai_feedback', sa.Text(), nullable=True))
    
    if 'ai_graded_at' not in existing_columns:
        op.add_column('student_simulation_instances', 
                      sa.Column('ai_graded_at', sa.DateTime(timezone=True), nullable=True))
    
    # Add grade status field if it doesn't exist
    if 'grade_status' not in existing_columns:
        op.add_column('student_simulation_instances', 
                      sa.Column('grade_status', sa.String(), nullable=True, server_default='not_graded'))
    
    # Check existing indexes
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('student_simulation_instances')]
    
    # Add index for grade status if it doesn't exist
    if 'idx_student_sim_instances_grade_status' not in existing_indexes:
        op.create_index('idx_student_sim_instances_grade_status', 
                        'student_simulation_instances', ['grade_status'])
    
    # Check if grade_history table already exists
    existing_tables = inspector.get_table_names()
    
    if 'grade_history' not in existing_tables:
        # Create grade_history table for audit trail
        op.create_table(
            'grade_history',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('instance_id', sa.Integer(), nullable=False),
            sa.Column('grade_type', sa.String(), nullable=False),  # 'ai' or 'professor'
            sa.Column('grade_value', sa.Float(), nullable=True),
            sa.Column('feedback', sa.Text(), nullable=True),
            sa.Column('graded_by', sa.Integer(), nullable=True),
            sa.Column('previous_status', sa.String(), nullable=True),
            sa.Column('new_status', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['instance_id'], ['student_simulation_instances.id'], ondelete='CASCADE'),
            sa.ForeignKeyConstraint(['graded_by'], ['users.id'], ondelete='SET NULL'),
            sa.PrimaryKeyConstraint('id')
        )
        
        # Create indexes for grade_history
        op.create_index('idx_grade_history_instance_id', 'grade_history', ['instance_id'])
        op.create_index('idx_grade_history_graded_by', 'grade_history', ['graded_by'])
        op.create_index('idx_grade_history_created_at', 'grade_history', ['created_at'])
        op.create_index('idx_grade_history_grade_type', 'grade_history', ['grade_type'])
    else:
        # Table exists, check if indexes exist
        grade_history_indexes = [idx['name'] for idx in inspector.get_indexes('grade_history')]
        
        if 'idx_grade_history_instance_id' not in grade_history_indexes:
            op.create_index('idx_grade_history_instance_id', 'grade_history', ['instance_id'])
        if 'idx_grade_history_graded_by' not in grade_history_indexes:
            op.create_index('idx_grade_history_graded_by', 'grade_history', ['graded_by'])
        if 'idx_grade_history_created_at' not in grade_history_indexes:
            op.create_index('idx_grade_history_created_at', 'grade_history', ['created_at'])
        if 'idx_grade_history_grade_type' not in grade_history_indexes:
            op.create_index('idx_grade_history_grade_type', 'grade_history', ['grade_type'])


def downgrade() -> None:
    # Drop grade_history table and indexes
    op.drop_index('idx_grade_history_grade_type', table_name='grade_history')
    op.drop_index('idx_grade_history_created_at', table_name='grade_history')
    op.drop_index('idx_grade_history_graded_by', table_name='grade_history')
    op.drop_index('idx_grade_history_instance_id', table_name='grade_history')
    op.drop_table('grade_history')
    
    # Drop grade_status index and column
    op.drop_index('idx_student_sim_instances_grade_status', table_name='student_simulation_instances')
    op.drop_column('student_simulation_instances', 'grade_status')
    
    # Drop AI grading fields
    op.drop_column('student_simulation_instances', 'ai_graded_at')
    op.drop_column('student_simulation_instances', 'ai_feedback')
    op.drop_column('student_simulation_instances', 'ai_grade')

