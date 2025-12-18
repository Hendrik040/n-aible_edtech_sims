"""fix_cohort_simulations_foreign_key

Revision ID: fix_cohort_simulations_fk
Revises: 97a4c4205c1b
Create Date: 2025-12-14 21:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fix_cohort_simulations_fk'
down_revision: Union[str, None] = 'rename_scenario_to_sim'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Fix cohort_simulations foreign key to reference simulations table.
    
    This migration fixes the foreign key constraint that may have been missed
    when the scenarios table was renamed to simulations.
    """
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    # Check if cohort_simulations table exists
    if 'cohort_simulations' not in inspector.get_table_names():
        return
    
    # Check if simulations table exists (if not, the rename migration hasn't run)
    if 'simulations' not in inspector.get_table_names():
        # If simulations doesn't exist, check if scenarios exists
        if 'scenarios' in inspector.get_table_names():
            # Rename migration hasn't run yet, nothing to fix
            return
        else:
            # Neither table exists, skip
            return
    
    # Get all foreign key constraints on cohort_simulations
    fk_constraints = inspector.get_foreign_keys('cohort_simulations')
    
    # Find the constraint that references scenarios/simulations
    for fk in fk_constraints:
        if 'simulation_id' in fk['constrained_columns']:
            referred_table = fk.get('referred_table')
            constraint_name = fk.get('name', '')
            
            # Check if it references the old table name
            if referred_table == 'scenarios':
                # Drop the old constraint and create new one
                op.drop_constraint(
                    constraint_name,
                    'cohort_simulations',
                    type_='foreignkey'
                )
                # Check if the new constraint already exists before creating
                existing_fks = inspector.get_foreign_keys('cohort_simulations')
                constraint_exists = any(
                    fk2.get('name') == 'fk_cohort_simulations_simulation_id_simulations'
                    for fk2 in existing_fks
                )
                if not constraint_exists:
                    op.create_foreign_key(
                        'fk_cohort_simulations_simulation_id_simulations',
                        'cohort_simulations', 'simulations',
                        ['simulation_id'], ['id']
                    )
                break
            elif referred_table == 'simulations':
                # Already correct - check if constraint name needs updating
                if constraint_name != 'fk_cohort_simulations_simulation_id_simulations':
                    # Only update if the name is wrong
                    op.drop_constraint(constraint_name, 'cohort_simulations', type_='foreignkey')
                    existing_fks = inspector.get_foreign_keys('cohort_simulations')
                    constraint_exists = any(
                        fk2.get('name') == 'fk_cohort_simulations_simulation_id_simulations'
                        for fk2 in existing_fks
                    )
                    if not constraint_exists:
                        op.create_foreign_key(
                            'fk_cohort_simulations_simulation_id_simulations',
                            'cohort_simulations', 'simulations',
                            ['simulation_id'], ['id']
                        )
                # If it's already correct, do nothing
                break


def downgrade() -> None:
    """
    Revert the foreign key fix (not typically needed).
    """
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    
    if 'cohort_simulations' in inspector.get_table_names():
        # Drop the simulations constraint
        fk_constraints = inspector.get_foreign_keys('cohort_simulations')
        for fk in fk_constraints:
            if fk.get('name') == 'fk_cohort_simulations_simulation_id_simulations':
                op.drop_constraint(
                    'fk_cohort_simulations_simulation_id_simulations',
                    'cohort_simulations',
                    type_='foreignkey'
                )
                break
        # Recreate constraint pointing to scenarios (if downgrading)
        if 'scenarios' in inspector.get_table_names():
            op.create_foreign_key(
                'fk_cohort_simulations_simulation_id_scenarios',
                'cohort_simulations', 'scenarios',
                ['simulation_id'], ['id']
            )
