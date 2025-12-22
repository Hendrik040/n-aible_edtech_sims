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
from common.services.simulation_queue_service import (
    dequeue_job,
    mark_job_completed,
    mark_job_failed,
)
from modules.simulation.service import SimulationService
from modules.simulation.repository import SimulationRepository

logger = logging.getLogger(__name__)

# Worker configuration
POLL_INTERVAL = 1.0  # Seconds between queue polls
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "5"))  # Max concurrent jobs per worker

# Track active tasks to prevent garbage collection
active_tasks: set = set()




async def process_simulation_job(job_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
    """
    Process a single simulation job.
    
    Args:
        job_data: Job data dictionary
        db: Database session
        
    Returns:
        Result dictionary with streaming chunks
    """
    job_id = job_data["job_id"]
    user_id = job_data["user_id"]
    user_progress_id = job_data["user_progress_id"]
    message = job_data["message"]
    scene_id = job_data.get("scene_id")
    
    try:
        # Initialize services
        repository = SimulationRepository(db)
        service = SimulationService(db)
        
        # Collect streaming chunks
        chunks = []
        
        # Process the chat message using the existing streaming handler
        async for chunk in service.stream_chat_message(
            user_id=user_id,
            user_progress_id=user_progress_id,
            message=message,
            scene_id=scene_id
        ):
            chunks.append(chunk)
        
        return {
            "chunks": chunks,
            "success": True
        }
        
    except Exception as e:
        logger.error(f"[SIMULATION_WORKER] Error processing job {job_id}: {e}", exc_info=True)
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
                
                logger.info(f"[SIMULATION_WORKER] Job completed: job_id={job_id}")
                
            except Exception as e:
                logger.error(f"[SIMULATION_WORKER] Job failed: job_id={job_id}, error={e}", exc_info=True)
                await mark_job_failed(job_id, str(e), retry=True)
            finally:
                db.close()
    
    while True:
        try:
            job_data = await dequeue_job()
            
            if job_data:
                job_id = job_data["job_id"]
                logger.info(f"[SIMULATION_WORKER] Processing job: job_id={job_id}")
                
                # Create task and keep reference to prevent garbage collection
                task = asyncio.create_task(process_with_semaphore(job_data))
                active_tasks.add(task)
                
                # Remove task from set when it completes
                task.add_done_callback(lambda t: active_tasks.discard(t))
            else:
                await asyncio.sleep(POLL_INTERVAL)
                
        except Exception as e:
            logger.error(f"[SIMULATION_WORKER] Error in queue processing loop: {e}", exc_info=True)
            await asyncio.sleep(POLL_INTERVAL)
