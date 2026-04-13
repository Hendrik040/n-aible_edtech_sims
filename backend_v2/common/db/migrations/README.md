# Database Migrations

This directory contains Alembic database migrations for the modular backend architecture.

## Structure

```
migrations/
├── env.py              # Alembic environment configuration
├── script.py.mako      # Migration template
├── versions/           # Migration version files
└── README.md          # This file
```

## Configuration

- **Alembic config**: `../alembic.ini` (at backend root)
- **Database URL**: Loaded from `common.config.get_settings()`
- **Models**: Imported from all modules in `env.py`

## Usage

### Create a New Migration

```bash
# From the backend directory
cd /path/to/n-aible_edtech_sims/backend

# Create migration with autogenerate
alembic revision --autogenerate -m "description of changes"

# Or create empty migration
alembic revision -m "description of changes"
```

### Apply Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply one migration
alembic upgrade +1

# Apply to specific revision
alembic upgrade <revision_id>
```

### Rollback Migrations

```bash
# Rollback one migration
alembic downgrade -1

# Rollback to specific revision
alembic downgrade <revision_id>

# Rollback all migrations
alembic downgrade base
```

### Check Migration Status

```bash
# Show current database version
alembic current

# Show migration history
alembic history

# Show pending migrations
alembic heads
```

## Adding New Models

When you add models to a new module:

1. **Create the model** in `modules/<module_name>/models.py`
2. **Import it in `migrations/env.py`**:
   ```python
   from modules.<module_name> import models as <module_name>_models  # noqa: F401
   ```
3. **Create migration**:
   ```bash
   alembic revision --autogenerate -m "add <module_name> models"
   ```

## Best Practices

1. **Always review auto-generated migrations** before applying
2. **Test migrations** on development database first
3. **Use descriptive migration messages**
4. **Never edit existing migration files** - create new ones instead
5. **Keep migrations small and focused** - one logical change per migration
6. **Test rollback** to ensure migrations are reversible

## Example Workflow

```bash
# 1. Make changes to models
# Edit modules/auth/models.py

# 2. Create migration
alembic revision --autogenerate -m "add user profile fields"

# 3. Review the generated migration file
# Check migrations/versions/YYYYMMDD_HHMM-xxxxx_add_user_profile_fields.py

# 4. Apply migration
alembic upgrade head

# 5. Verify changes
# Check database schema matches your models
```

