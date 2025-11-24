"""
Pytest configuration for test discovery and setup.
"""
import sys
from pathlib import Path

# Add the backend directory to Python path so tests can import modules
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))
