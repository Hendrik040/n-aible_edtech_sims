"""
Load backend/.env before sandbox scaling tests run.
This means DAYTONA_API_KEY (and any other vars) set in the root .env
are available without needing to export them manually in the shell.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# backend/.env  (two levels up from this conftest)
_env_path = Path(__file__).resolve().parents[2] / ".env"
load_dotenv(_env_path, override=False)  # override=False: shell env takes precedence
