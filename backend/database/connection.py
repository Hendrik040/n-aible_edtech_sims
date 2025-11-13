from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pydantic_settings import BaseSettings
from typing import Optional
from contextlib import contextmanager
import os
from pathlib import Path

# Get the project root directory where .env file is located
project_root = Path(__file__).parent.parent.parent

class Settings(BaseSettings):
    # Use DATABASE_URL from environment (Railway provides this), fallback to localhost for development
    database_url: str = os.getenv("DATABASE_URL", "postgresql://localhost:5432/ai_agent_platform")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    serper_api_key: str = os.getenv("SERPER_API_KEY", "")
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    secret_key: str = os.getenv("SECRET_KEY", "your-secret-key-here")
    environment: str = os.getenv("ENVIRONMENT", "development")
    cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173")
    llamaparse_api_key: Optional[str] = os.getenv("LLAMAPARSE_API_KEY", None)
    gemini_api_key: Optional[str] = None
    freepik_api_key: Optional[str] = os.getenv("FREEPIK_API_KEY", None)
    # Support both Wasabi and AWS S3 - AWS takes precedence if both are set
    aws_access_key_id: Optional[str] = os.getenv("AWS_ACCESS_KEY_ID", None)
    aws_secret_access_key: Optional[str] = os.getenv("AWS_SECRET_ACCESS_KEY", None)
    aws_bucket_name: Optional[str] = os.getenv("AWS_BUCKET_NAME", None)
    aws_region: Optional[str] = os.getenv("AWS_REGION", "us-east-1")
    aws_public_read: bool = os.getenv("AWS_PUBLIC_READ", "false").lower() == "true"
    
    # Legacy Wasabi support (for backward compatibility)
    wasabi_access_key_id: Optional[str] = os.getenv("WASABI_ACCESS_KEY_ID", None)
    wasabi_secret_access_key: Optional[str] = os.getenv("WASABI_SECRET_ACCESS_KEY", None)
    wasabi_bucket_name: Optional[str] = os.getenv("WASABI_BUCKET_NAME", None)
    wasabi_endpoint_url: Optional[str] = os.getenv("WASABI_ENDPOINT_URL", None)
    wasabi_public_read: bool = os.getenv("WASABI_PUBLIC_READ", "false").lower() == "true"
    
    # Computed properties - AWS takes precedence
    @property
    def s3_access_key_id(self) -> Optional[str]:
        return self.aws_access_key_id or self.wasabi_access_key_id
    
    @property
    def s3_secret_access_key(self) -> Optional[str]:
        return self.aws_secret_access_key or self.wasabi_secret_access_key
    
    @property
    def s3_bucket_name(self) -> Optional[str]:
        return self.aws_bucket_name or self.wasabi_bucket_name
    
    @property
    def s3_endpoint_url(self) -> Optional[str]:
        # AWS doesn't need endpoint_url (uses defaults), Wasabi does
        if self.aws_access_key_id:
            return None  # AWS uses default endpoints
        return self.wasabi_endpoint_url.rstrip('/') if self.wasabi_endpoint_url else None
    
    @property
    def s3_public_read(self) -> bool:
        return self.aws_public_read or self.wasabi_public_read
    
    @property
    def s3_region(self) -> str:
        return self.aws_region if self.aws_access_key_id else "us-east-1"
    
    @property
    def is_aws(self) -> bool:
        return bool(self.aws_access_key_id)
    
    # Backend URL for webhooks
    backend_url: str = os.getenv("BACKEND_URL", "http://localhost:8001")
    
    # Google OAuth settings
    google_client_id: str = os.getenv("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.getenv("GOOGLE_CLIENT_SECRET", "")
    google_redirect_uri: str = os.getenv("GOOGLE_REDIRECT_URI", "")
    
    # Vector database configuration
    use_pgvector: bool = os.getenv("USE_PGVECTOR", "true").lower() == "true"
    
    class Config:
        env_file = project_root / ".env"  # Look for .env in project root
        extra = "ignore"  # Ignore extra environment variables

settings = Settings()

# Validate environment settings
def _validate_environment():
    """Validate environment settings for production"""
    if settings.environment == "production":
        if not settings.google_client_id or not settings.google_client_id.strip():
            raise RuntimeError("GOOGLE_CLIENT_ID is required in production environment")
        if not settings.google_client_secret or not settings.google_client_secret.strip():
            raise RuntimeError("GOOGLE_CLIENT_SECRET is required in production environment")
        if not settings.google_redirect_uri or not settings.google_redirect_uri.strip():
            raise RuntimeError("GOOGLE_REDIRECT_URI is required in production environment")
        if "localhost" in settings.google_redirect_uri:
            raise RuntimeError("GOOGLE_REDIRECT_URI cannot use localhost in production environment")
        # Check for either AWS or Wasabi credentials
        if not settings.s3_access_key_id or not settings.s3_access_key_id.strip():
            raise RuntimeError("AWS_ACCESS_KEY_ID or WASABI_ACCESS_KEY_ID is required in production environment")
        if not settings.s3_secret_access_key or not settings.s3_secret_access_key.strip():
            raise RuntimeError("AWS_SECRET_ACCESS_KEY or WASABI_SECRET_ACCESS_KEY is required in production environment")
        if not settings.s3_bucket_name or not settings.s3_bucket_name.strip():
            raise RuntimeError("AWS_BUCKET_NAME or WASABI_BUCKET_NAME is required in production environment")
        # Endpoint URL only required for Wasabi, not AWS
        if not settings.is_aws and (not settings.s3_endpoint_url or not settings.s3_endpoint_url.strip()):
            raise RuntimeError("WASABI_ENDPOINT_URL is required in production environment when using Wasabi")

# Validation is now called from application startup instead of import time

# Print loaded settings securely - only in non-production
from utilities.secure_logging import secure_print_api_key_status, secure_print_database_url

if settings.environment != "production":
    print(f"🌍 Environment: {settings.environment}")
    secure_print_api_key_status("OpenAI API Key", settings.openai_api_key, settings.environment)
    secure_print_api_key_status("Secret Key", settings.secret_key, settings.environment)
    secure_print_database_url(settings.database_url, settings.environment)
    provider = "AWS" if settings.is_aws else "Wasabi"
    secure_print_api_key_status(f"{provider} Access Key", settings.s3_access_key_id, settings.environment)
    secure_print_api_key_status(f"{provider} Bucket", settings.s3_bucket_name, settings.environment)

# Database setup with SSL and connection pooling
if settings.database_url.startswith("postgresql"):
    # Increased pool size to handle high concurrent user load
    # pool_size: base connections maintained
    # max_overflow: additional connections beyond pool_size
    # Total max connections = pool_size + max_overflow = 50 + 40 = 90
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,  # Verify connections before use
        pool_recycle=300,    # Recycle connections every 5 minutes
        pool_size=70,        # Number of connections to maintain (increased from 20)
        max_overflow=80,     # Maximum connections beyond pool_size (increased from 30)
        pool_timeout=60,     # Timeout for getting connection from pool
        connect_args={
            "connect_timeout": 30,  # Connection timeout
            "application_name": "AOM_2025_Backend"
        }
    )
elif settings.database_url.startswith("sqlite"):
    # Use simpler engine for SQLite (development only)
    print("⚠️  WARNING: Using SQLite for development. PostgreSQL recommended for production.")
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False}
    )
else:
    raise ValueError("Unsupported database URL format. Only PostgreSQL and SQLite are supported.")

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create declarative base for models
Base = declarative_base()

def get_db():
    """Database dependency for FastAPI endpoints"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def get_db_session():
    """
    Context manager for getting database sessions outside of FastAPI dependencies.
    Use this instead of next(get_db()) to ensure proper connection management.
    
    Usage:
        with get_db_session() as db:
            # use db here
            pass
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close() 