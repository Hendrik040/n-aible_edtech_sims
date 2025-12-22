"""
Simulation Worker Tasks.

Background worker that processes queued simulation chat requests.
"""

import asyncio
import os
import logging
from typing import Dict, Any

from sqlalchemy.orm import Session
from common.db.core import SessionLocal
from common.config import get_settings
from common.services.simulation_queue_service import (
    dequeue_job,
    mark_job_completed,
    mark_job_failed,
)
from modules.simulation.service import SimulationService
from modules.simulation.repository import SimulationRepository

logger = logging.getLogger(__name__)

# Environment check for development-only logging
settings = get_settings()
_is_dev = settings.environment != "production"

# Worker configuration
POLL_INTERVAL = 1.0  # Seconds between queue polls
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "5"))  # Max concurrent jobs per worker

# Track active tasks to prevent garbage collection
active_tasks: set = set()




async def process_simulation_job(job_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    Process a single simulation job (chat or grading).
    
    Args:
        job_data: Job data dictionary
        db: Database session
        
    Returns:
        Result dictionary with job results
    """
    job_id = job_data["job_id"]
    user_id = job_data["user_id"]
    user_progress_id = job_data["user_progress_id"]
    job_type = job_data.get("job_type", "chat")
    session_id = job_data.get("session_id")
    
    try:
        # Initialize services
        service = SimulationService(db)
        
        if job_type == "grading":
            # Process grading job
            if _is_dev:
                session_log = f", session_id={session_id}" if session_id else ""
                logger.info(
                    f"[SIMULATION_WORKER] Processing grading job: job_id={job_id}, "
                    f"user_progress_id={user_progress_id}{session_log}"
                )
            grading_result = await service.get_simulation_grading(user_progress_id, user_id)
            
            return {
                "grading": grading_result,
                "success": True
            }
        else:
            # Process chat job (existing behavior)
            message = job_data["message"]
            scene_id = job_data.get("scene_id")
            
            # Log initial state - check conversation logs before processing
            from common.db.models import ConversationLog
            initial_log_count = db.query(ConversationLog).filter(
                ConversationLog.user_progress_id == user_progress_id
            ).count()
            
            if _is_dev:
                session_log = f", session_id={session_id}" if session_id else ""
                logger.info(
                    f"[SIMULATION_WORKER] Processing chat job: job_id={job_id}, "
                    f"user_id={user_id}, user_progress_id={user_progress_id}, "
                    f"message='{message[:50]}...', initial_log_count={initial_log_count}{session_log}"
                )
            
            # Collect streaming chunks
            chunks = []
            
            # Process the chat message using the existing streaming handler
            # CRITICAL: Fully consume the generator to ensure all database commits happen
            async for chunk in service.stream_chat_message(
                user_id=user_id,
                user_progress_id=user_progress_id,
                message=message,
                scene_id=scene_id
            ):
                chunks.append(chunk)
            
            # CRITICAL: Ensure database session commits all changes
            # The service.stream_chat_message() commits internally, and the callback handler
            # also commits persona responses. However, we need to ensure the worker's session
            # commits to persist all conversation logs (including those saved by chat handler via flush)
            try:
                # Verify that conversation logs were actually saved
                from common.db.models import ConversationLog
                conversation_count_before_commit = db.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress_id
                ).count()
                
                # Refresh the session to see any changes from other commits
                db.expire_all()
                # Commit any pending changes (e.g., from chat handler's flush() calls)
                db.commit()
                
                # Verify conversation logs after commit (use a fresh query to ensure we see committed data)
                # Create a new query after commit to see the actual database state
                conversation_count_after = db.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress_id
                ).count()
                
                # Get recent conversation logs to verify they were saved
                recent_logs = db.query(ConversationLog).filter(
                    ConversationLog.user_progress_id == user_progress_id
                ).order_by(ConversationLog.message_order.desc()).limit(5).all()
                
                recent_log_summary = [
                    f"{log.message_type}:{log.sender_name}:{len(log.message_content)}chars"
                    for log in recent_logs
                ]
                
                logger.info(
                    f"[SIMULATION_WORKER] Committed database session for job {job_id}: "
                    f"user_progress_id={user_progress_id}, "
                    f"conversation_logs: initial={initial_log_count}, before_commit={conversation_count_before_commit}, "
                    f"after_commit={conversation_count_after}, recent_logs={recent_log_summary}"
                )
                
                if conversation_count_after == 0:
                    logger.error(
                        f"[SIMULATION_WORKER] ERROR: No conversation logs found for user_progress_id={user_progress_id} "
                        f"after processing job {job_id}. Messages were NOT saved!"
                    )
                elif conversation_count_after == initial_log_count:
                    logger.warning(
                        f"[SIMULATION_WORKER] WARNING: Conversation log count did not increase "
                        f"(initial={initial_log_count}, after={conversation_count_after}) "
                        f"for user_progress_id={user_progress_id}, job {job_id}. "
                        f"New messages may not have been saved! Message was: '{message[:100]}...'"
                    )
                else:
                    logger.info(
                        f"[SIMULATION_WORKER] ✓ Successfully saved {conversation_count_after - initial_log_count} "
                        f"new conversation log(s) for user_progress_id={user_progress_id}, job {job_id}"
                    )
            except Exception as e:
                logger.error(
                    f"[SIMULATION_WORKER] Failed to commit database session after processing job {job_id}: {e}",
                    exc_info=True
                )
                db.rollback()
                raise
            
            if _is_dev:
                session_log = f", session_id={session_id}" if session_id else ""
                logger.info(
                    f"[SIMULATION_WORKER] Completed chat job: job_id={job_id}, "
                    f"chunks={len(chunks)}{session_log}"
                )
            
            return {
                "chunks": chunks,
                "success": True
            }
        
    except Exception as e:
        logger.error(
            f"[SIMULATION_WORKER] Error processing job {job_id}: {e}, "
            f"session_id={session_id}, user_id={user_id}, "
            f"user_progress_id={user_progress_id}",
            exc_info=True
        )
        raise


async def process_simulation_queue():
    """
    Enhanced version that stores results properly.
    
    This version processes jobs and stores results in Redis for retrieval.
    Tasks are tracked to prevent garbage collection.
    """
    logger.info("[SIMULATION_WORKER] Starting simulation queue worker")
    
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)
    
    async def process_with_semaphore(job_data: Dict[str, Any]):
        """Process a job with semaphore control and result storage."""
        async with semaphore:
            db = SessionLocal()
            job_id = job_data["job_id"]
            
            try:
                # Process the job
                result = await process_simulation_job(job_data, db)
                
                # Mark as completed with result
                await mark_job_completed(job_id, result)
                
                if _is_dev:
                    session_id = job_data.get("session_id")
                    session_log = f", session_id={session_id}" if session_id else ""
                    logger.info(f"[SIMULATION_WORKER] Job completed: job_id={job_id}{session_log}")
                
            except Exception as e:
                session_id = job_data.get("session_id")
                # Always log session_id in errors for debugging
                session_log = f", session_id={session_id}" if session_id else ", session_id=None"
                logger.error(
                    f"[SIMULATION_WORKER] Job failed: job_id={job_id}{session_log}, error={e}",
                    exc_info=True
                )
                await mark_job_failed(job_id, str(e), retry=True)
            finally:
                db.close()
    
    while True:
        try:
            job_data = await dequeue_job()
            
            if job_data:
                job_id = job_data["job_id"]
                # Log at INFO level so we can see when jobs are being processed
                logger.info(f"[SIMULATION_WORKER] Dequeued job: job_id={job_id}, user_progress_id={job_data.get('user_progress_id')}, message='{job_data.get('message', '')[:50]}...'")
                
                # Create task and keep reference to prevent garbage collection
                task = asyncio.create_task(process_with_semaphore(job_data))
                active_tasks.add(task)
                
                # Remove task from set when it completes
                task.add_done_callback(lambda t: active_tasks.discard(t))
            else:
                # Log periodically that we're polling (every 10 seconds to avoid spam)
                import time
                if not hasattr(process_simulation_queue, '_last_poll_log'):
                    process_simulation_queue._last_poll_log = 0
                now = time.time()
                if now - process_simulation_queue._last_poll_log > 10:
                    logger.debug(f"[SIMULATION_WORKER] Polling queue (no jobs available), active_tasks={len(active_tasks)}")
                    process_simulation_queue._last_poll_log = now
                await asyncio.sleep(POLL_INTERVAL)
                
        except Exception as e:
            logger.error(f"[SIMULATION_WORKER] Error in queue processing loop: {e}", exc_info=True)
            await asyncio.sleep(POLL_INTERVAL)
