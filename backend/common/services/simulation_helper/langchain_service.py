"""
LangChain Configuration Service for AI Agent Education Platform
Centralized configuration for all LangChain components
"""
import os
import warnings
# Suppress LangChain JSONB deprecation warning until LangChain updates
warnings.filterwarnings('ignore', category=DeprecationWarning, module='langchain.*')
warnings.filterwarnings('ignore', message='Please use JSONB instead of JSON for metadata')
from typing import Dict, Any

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from langchain_postgres import PGVector

from langchain.memory import ConversationBufferWindowMemory, ConversationSummaryBufferMemory
try:
    from langchain_community.cache import RedisCache, InMemoryCache
except ImportError:
    # Fallback for older LangChain versions
    from langchain.cache import RedisCache, InMemoryCache
from langchain.globals import set_llm_cache
import redis

from common.config import get_settings


class LangChainSettings(BaseSettings):
    """LangChain-specific settings"""
    
    # OpenAI Configuration
    openai_api_key: str
    openai_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"
    
    # PostgreSQL with pgvector
    postgres_url: str
    vector_collection_name: str = "ai_agent_embeddings"
    
    # Redis Configuration for Caching
    redis_url: str = "redis://localhost:6379/0"
    redis_enabled: bool = True
    
    # Embedding Configuration
    embedding_model: str = "openai"
    
    # Memory Configuration
    conversation_window_size: int = 10
    summary_threshold: int = 5
    max_token_limit: int = 2000
    
    # Performance Settings
    chunk_size: int = 1000
    chunk_overlap: int = 200
    similarity_threshold: float = 0.7
    max_retrieval_docs: int = 5
    
    # Session Management
    session_timeout: int = 3600  # 1 hour
    cache_ttl: int = 1800  # 30 minutes
    
    class Config:
        env_file = ".env"
        env_prefix = "LANGCHAIN_"
        extra = "ignore"  # Ignore extra fields


# Get settings from common.config
config = get_settings()

# Initialize settings with config values and environment overrides
settings = LangChainSettings(
    openai_api_key=config.openai_api_key,
    postgres_url=config.database_url,
    redis_enabled=False  # Disable Redis by default (use cache_service.py instead)
)


class LangChainManager:
    """Centralized LangChain component manager"""
    
    def __init__(self):
        # Removed _llm caching - now creates fresh instance per request for isolation
        self._embeddings = None
        self._vectorstore = None
        self._redis_client = None
        self._cache = None
        
    @property
    def llm(self) -> ChatOpenAI:
        """Create a fresh LLM instance per request for isolation.
        
        This ensures complete isolation between concurrent requests and prevents
        any potential state leakage from callbacks, streaming, or retry mechanisms.
        The overhead is minimal (~1ms) compared to LLM call latency (10-30s).
        """
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.7,
            max_tokens=1000,
            streaming=True
        )
    
    def create_fresh_llm(self) -> ChatOpenAI:
        """Create a fresh, isolated LLM instance for persona isolation"""
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.7,
            max_tokens=1000,
            streaming=True
        )

    def get_grading_llm(self) -> ChatOpenAI:
        """Create an LLM instance configured for grading with higher token limit.

        Grading requires structured JSON output (rubric scores, feedback per criterion)
        which can exceed the default 1000 token limit, causing JSON truncation failures.
        Streaming is disabled since grading uses structured output parsing.
        """
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.7,
            max_tokens=4096,
            streaming=False
        )
    
    @property
    def embeddings(self):
        """Get or create OpenAI embeddings instance"""
        if self._embeddings is None:
            model_name = getattr(settings, "openai_embedding_model", "text-embedding-3-small")
            self._embeddings = OpenAIEmbeddings(
                model=model_name,
                api_key=getattr(settings, "openai_api_key", None)
            )
        return self._embeddings
    
    @property
    def vectorstore(self):
        """Get or create PostgreSQL vector store.

        We keep the PGVector engine's pool small so it plays nicely with
        Neon/PgBouncer and does not compete aggressively with the main app
        engine for connections.
        """
        if self._vectorstore is None:
            try:
                engine_args: Dict[str, Any] = {
                    # Always pre-ping to detect stale connections quickly
                    "pool_pre_ping": True,
                }

                # Check if using Neon's pooled connection (PgBouncer)
                # Pooled connections have "-pooler" in the hostname
                is_pooled_connection = "-pooler" in settings.postgres_url or "pooler" in settings.postgres_url.lower()
                
                if settings.postgres_url.startswith("postgresql"):
                    if is_pooled_connection:
                        # Use NullPool for pooled connections - let PgBouncer handle pooling
                        from sqlalchemy.pool import NullPool
                        engine_args.update({
                            "poolclass": NullPool,
                            "pool_reset_on_return": None,  # Don't rollback - connections are closed immediately
                        })
                    else:
                        # Use client-side pool for direct connections
                        # Increased pool size to support 50+ concurrent users:
                        # 50 users × ~2-3 vector queries per LLM call = 100-150 ops
                        # Pool of 20 + overflow 10 = 30 max connections handles this load
                        pool_size = int(os.getenv("PGVECTOR_POOL_SIZE", "20"))
                        max_overflow = int(os.getenv("PGVECTOR_MAX_OVERFLOW", "10"))
                        # Increased timeout to 30s to prevent immediate failures under pressure
                        pool_timeout = int(os.getenv("PGVECTOR_POOL_TIMEOUT", "30"))

                        engine_args.update(
                            {
                                "pool_size": pool_size,
                                "max_overflow": max_overflow,
                                "pool_recycle": 300,
                                "pool_timeout": pool_timeout,
                            }
                        )

                self._vectorstore = PGVector(
                    connection=settings.postgres_url,
                    embeddings=self.embeddings,
                    collection_name=settings.vector_collection_name,
                    use_jsonb=True,
                    engine_args=engine_args,
                )
            except Exception as e:
                print(f"Failed to initialize PGVector: {e}")
                return None
        return self._vectorstore
    
    @property
    def redis_client(self):
        """Get or create Redis client"""
        if self._redis_client is None and settings.redis_enabled:
            try:
                self._redis_client = redis.from_url(settings.redis_url)
                # Test connection
                self._redis_client.ping()
            except Exception as e:
                print(f"Redis connection failed: {e}. Using in-memory cache.")
                self._redis_client = None
        return self._redis_client
    
    @property
    def cache(self):
        """Get or create cache instance"""
        if self._cache is None:
            if self.redis_client:
                self._cache = RedisCache(redis_client=self.redis_client)
            else:
                self._cache = InMemoryCache()
            set_llm_cache(self._cache)
        return self._cache
    
    def create_conversation_memory(self, 
                                 session_id: str,
                                 memory_type: str = "buffer_window"):
        """Create conversation memory for a session"""
        if memory_type == "buffer_window":
            return ConversationBufferWindowMemory(
                k=settings.conversation_window_size,
                return_messages=True,
                memory_key="chat_history"
            )
        elif memory_type == "summary_buffer":
            return ConversationSummaryBufferMemory(
                llm=self.llm,
                max_token_limit=settings.max_token_limit,
                return_messages=True,
                memory_key="chat_history"
            )
        else:
            raise ValueError(f"Unknown memory type: {memory_type}")
    
    def get_session_key(self, user_id: int, scenario_id: int, scene_id: int) -> str:
        """Generate session key for caching"""
        return f"session:{user_id}:{scenario_id}:{scene_id}"
    
    def get_embedding_key(self, content_type: str, content_id: int) -> str:
        """Generate embedding key for caching"""
        return f"embedding:{content_type}:{content_id}"


# Global LangChain manager instance
langchain_manager = LangChainManager()

# Initialize cache
langchain_manager.cache

# Export commonly used components
# Note: Do NOT import llm from this module - it would create a single instance at import time.
# Instead, access via langchain_manager.llm (creates fresh instance per access) 
# or use langchain_manager.create_fresh_llm() for explicit creation.
embeddings = langchain_manager.embeddings
# Don't initialize vectorstore at module level - it will try to connect to DB
# vectorstore = langchain_manager.vectorstore  # Access via langchain_manager.vectorstore when needed
cache = langchain_manager.cache


def get_langchain_manager() -> LangChainManager:
    """Dependency injection for LangChain manager"""
    return langchain_manager

