from contextlib import asynccontextmanager
import asyncio
import json
import logging
from sqlalchemy import text
from fastapi import FastAPI
from common.db.connection import engine

logger = logging.getLogger(__name__)

def _asyncio_exception_handler(loop, context):
    """
    Global asyncio exception handler to catch unhandled exceptions in tasks.
    This prevents StopAsyncIteration and other normal async generator exceptions
    from being logged as errors.
    """
    exception = context.get('exception')
    if isinstance(exception, StopAsyncIteration):
        # StopAsyncIteration is normal when async generators finish - ignore it
        return
    elif isinstance(exception, asyncio.CancelledError):
        # CancelledError is normal when tasks are cancelled - ignore it
        return
    
    # Log other exceptions
    message = context.get('message', 'Unhandled exception in asyncio task')
    logger.debug(f"Asyncio task exception: {message}", exc_info=exception)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    Handles startup and shutdown events.
    """
    # Set up global asyncio exception handler to catch unhandled task exceptions
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_asyncio_exception_handler)
    
    # Startup: Test database connection
    # Note: We use migrations for schema, so we don't auto-create tables here
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection verified successfully")
    except Exception as e:
        logger.error(f"Database connection failed during startup: {e}", exc_info=True)
        # Log the database URL (masked for security)
        from common.config import get_settings
        settings = get_settings()
        db_url = settings.database_url
        if len(db_url) > 20:
            masked_url = db_url[:10] + "..." + db_url[-10:]
        else:
            masked_url = "***"
        logger.error(f"Database URL (masked): {masked_url}")
        # Don't crash - let the app start and handle DB errors at request time
        # But log it prominently so we can see it in Railway logs
    
    # Startup: Start image upload worker as background task
    image_worker_task = None
    try:
        from modules.publishing.tasks import process_queue
        image_worker_task = asyncio.create_task(process_queue())
        logger.info("Image upload worker started successfully")
    except Exception as e:
        logger.error(f"Failed to start image upload worker: {e}", exc_info=True)
        # Don't crash - app can still function, but image uploads won't be processed
    
    # Startup: Start simulation queue worker as background task
    simulation_worker_task = None
    try:
        from modules.simulation.tasks import process_simulation_queue
        simulation_worker_task = asyncio.create_task(process_simulation_queue())
        logger.info("Simulation queue worker started successfully")
    except Exception as e:
        logger.error(f"Failed to start simulation queue worker: {e}", exc_info=True)
        # Don't crash - app can still function, but queued simulations won't be processed
    
    # Startup: Start Redis pub/sub subscriber for simulation progress notifications
    pubsub_task = None
    try:
        from common.services.cache_service import redis_manager
        if redis_manager.redis:
            pubsub_task = asyncio.create_task(_redis_subscriber())
            logger.info("Redis pub/sub subscriber started successfully")
        else:
            logger.warning("Redis not available, skipping pub/sub subscriber")
    except Exception as e:
        logger.error(f"Failed to start Redis subscriber: {e}", exc_info=True)
        # Don't crash - app can still function, but cross-server notifications won't work
    
    # Startup: Start session cleanup task
    cleanup_task = None
    try:
        cleanup_task = asyncio.create_task(_session_cleanup_task())
        logger.info("Session cleanup task started successfully")
    except Exception as e:
        logger.error(f"Failed to start session cleanup task: {e}", exc_info=True)
        # Don't crash - app can still function, but expired sessions won't be cleaned up
    
    yield
    
    # Shutdown: Cancel image upload worker task gracefully
    if image_worker_task:
        logger.info("Stopping image upload worker...")
        image_worker_task.cancel()
        try:
            await image_worker_task
        except asyncio.CancelledError:
            logger.info("Image upload worker stopped")
        except Exception as e:
            logger.error(f"Error stopping image upload worker: {e}")
    
    # Shutdown: Cancel simulation worker task gracefully
    if simulation_worker_task:
        logger.info("Stopping simulation queue worker...")
        simulation_worker_task.cancel()
        try:
            await simulation_worker_task
        except asyncio.CancelledError:
            logger.info("Simulation queue worker stopped")
        except Exception as e:
            logger.error(f"Error stopping simulation queue worker: {e}")
    
    # Shutdown: Cancel Redis subscriber task gracefully
    if pubsub_task:
        logger.info("Stopping Redis subscriber...")
        pubsub_task.cancel()
        try:
            await pubsub_task
        except asyncio.CancelledError:
            logger.info("Redis subscriber stopped")
        except Exception as e:
            logger.error(f"Error stopping Redis subscriber: {e}")
    
    # Shutdown: Cancel session cleanup task gracefully
    if cleanup_task:
        logger.info("Stopping session cleanup task...")
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            logger.info("Session cleanup task stopped")
        except Exception as e:
            logger.error(f"Error stopping session cleanup task: {e}")
    
    # Shutdown: Clean up resources if needed
    # e.g. close DB connections, http clients, etc.
    logger.info("Application shutting down")


async def _redis_subscriber():
    """
    Redis pub/sub subscriber for simulation status updates.
    
    Listens for notifications when simulations are ready and forwards them
    to local WebSocket connections. This enables multi-server support.
    """
    from common.services.cache_service import redis_manager
    
    if not redis_manager.redis:
        return
    
    try:
        pubsub = redis_manager.redis.pubsub()
        # Subscribe to pattern: user:*:simulations
        pubsub.psubscribe("user:*:simulations")
        logger.info("Redis subscriber listening on pattern: user:*:simulations")
        
        while True:
            try:
                # Run blocking Redis call in thread pool to avoid blocking event loop
                loop = asyncio.get_event_loop()
                message = await loop.run_in_executor(
                    None, 
                    lambda: pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                )
                
                if message is None:
                    await asyncio.sleep(0.1)  # Small sleep to prevent tight loop
                    continue
                
                if message["type"] == "pmessage":
                    data = message["data"]
                    
                    try:
                        notification = json.loads(data)
                        user_id = notification.get("user_id")
                        simulation_id = notification.get("simulation_id")
                        status = notification.get("status")
                        title = notification.get("title")
                        
                        if user_id:
                            logger.info(f"📨 Redis notification received: user={user_id}, sim={simulation_id}, status={status}")
                            # Forward to local WebSocket connection if user is connected to this server
                            from modules.publishing.router import send_simulation_notification
                            await send_simulation_notification(user_id, simulation_id, status, title)
                        else:
                            logger.warning(f"Redis notification missing user_id: {notification}")
                    except json.JSONDecodeError:
                        logger.warning(f"Failed to parse Redis message: {data}")
                    except Exception as e:
                        logger.error(f"Error processing Redis notification: {e}")
                        
            except asyncio.CancelledError:
                logger.info("Redis subscriber cancelled")
                break
            except Exception as e:
                logger.error(f"Error in Redis subscriber loop: {e}")
                await asyncio.sleep(1)  # Wait before retrying
                
    except Exception as e:
        logger.error(f"Redis subscriber error: {e}", exc_info=True)
    finally:
        try:
            pubsub.close()
        except Exception:
            pass


async def _session_cleanup_task():
    """
    Background task to clean up expired agent sessions.

    Runs every 5 minutes to mark expired sessions as inactive.
    """
    while True:
        try:
            # Count expired sessions and clean them up
            from common.db.core import SessionLocal
            from common.db.models import AgentSessions
            from datetime import datetime
            
            db = SessionLocal()
            try:
                expired_count = db.query(AgentSessions).filter(
                    AgentSessions.is_active.is_(True),
                    AgentSessions.expires_at < datetime.utcnow()
                ).count()

                if expired_count > 0:
                    db.query(AgentSessions).filter(
                        AgentSessions.is_active.is_(True),
                        AgentSessions.expires_at < datetime.utcnow()
                    ).update({"is_active": False}, synchronize_session=False)
                    db.commit()
                    logger.info(f"Cleaned up {expired_count} expired agent sessions")
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in session cleanup task: {e}")
        
        # Run cleanup every 5 minutes
        await asyncio.sleep(300)