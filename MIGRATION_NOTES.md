# Migration Notes

## Issue: Modified Existing Migration File

**Problem**: We modified the existing migration file `2025_12_13_1301-rename_scenario_to_simulation.py` instead of creating a new migration.

**Resolution**: 
- Reverted the migration file to match `develop-v2`
- The migration has already been applied to the database, so the database is in the correct state
- The defensive column checks we added are no longer in the migration file, but the database already has the correct foreign keys

**Note**: If applying migrations on a fresh database, the original migration might fail if certain columns don't exist. In that case, a new migration would need to be created to handle those edge cases.

## Files Modified

1. `backend/common/db/migrations/versions/2025_12_13_1301-rename_scenario_to_simulation.py` - Reverted to match develop-v2
2. Other files may have differences that need to be resolved during merge

## Best Practice Going Forward

- **Never modify existing migration files** once they've been applied
- Create new migration files for any changes needed
- Use `alembic revision` to create new migrations
- Use `alembic stamp` if you need to mark a migration as applied without running it

