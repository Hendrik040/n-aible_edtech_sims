# Development Tools

This directory contains development and administrative tools that should **NOT** be deployed to production environments.

## Contents

### Database Administration Tools

- **`db_admin/app.py`** - Flask-Admin web interface for database viewing
- **`db_admin/simple_viewer.py`** - Alternative Flask-based database viewer
- **`db_admin/templates/`** - HTML templates for the database viewers

**Security Warning:** These tools provide direct access to the database and should never be exposed in production.

### Deployment Scripts

- **`deploy_railway.py`** - Railway-specific deployment configuration script

## Usage

### Database Admin Tools

To run the database admin interface:

```bash
cd dev-tools/db_admin
python app.py
# or
python simple_viewer.py
```

Then navigate to `http://localhost:5000` in your browser.

**Note:** Ensure your DATABASE_URL environment variable is set correctly.

### Deployment Script

The Railway deployment script helps configure deployment settings:

```bash
cd dev-tools
python deploy_railway.py
```

## Important Notes

1. **Never commit credentials** - These tools may prompt for or display sensitive information
2. **Local use only** - These tools are for local development and debugging
3. **No production use** - Do not include this directory in production builds
4. **Access control** - When running locally, ensure proper firewall rules are in place

## Removed Files

The following files were removed during cleanup as they were no longer needed or were duplicates:

- `backend/clear_database.py` - Dangerous database wipe tool (removed for safety)
- `backend/cleanup_archives.py` - Duplicate cleanup functionality
- `backend/immediate_cleanup.py` - Duplicate cleanup script
- `backend/services/immediate_cleanup.py` - Dead code with non-functional stubs

## Production Alternatives

For production environments, use:

- **Database management**: Railway/Heroku dashboard or proper migration tools (Alembic)
- **Monitoring**: Application-level logging and metrics
- **Debugging**: Structured logging with proper log aggregation services
