-- Fix Alembic state to allow migrations to run
-- Run this in your Railway PostgreSQL database

-- Check current alembic version
SELECT version_num FROM alembic_version;

-- Reset to the version BEFORE the unique_id migration was supposed to run
-- The migration 82345087346c has down_revision = '1a44d8443d3f'
-- So we need to set the version to 1a44d8443d3f

UPDATE alembic_version SET version_num = '1a44d8443d3f';

-- Verify the change
SELECT version_num FROM alembic_version;

-- After this, restart your Railway backend service
-- The alembic upgrade head command in railway.toml will run the missing migrations

