"""
Professor service - Business logic for professor dashboard.
"""
import logging
from typing import Dict, List
from sqlalchemy.orm import Session

from .repository import ProfessorRepository
from .schemas import DashboardStatsResponse, ActivityItem
from common.services.cache_service import redis_manager

logger = logging.getLogger(__name__)


class ProfessorService:
    """Service for professor business logic."""
    
    def __init__(self, db: Session):
        self.repository = ProfessorRepository(db)
        self.db = db
    
    def get_dashboard_stats(self, professor_id: int) -> DashboardStatsResponse:
        """
        Get dashboard statistics for a professor.
        
        OPTIMIZATION: Uses Redis caching to reduce database load.
        Cache TTL: 5 minutes (300 seconds) - stats don't need to be real-time.
        """
        # Check cache first
        cache_key = f"professor:{professor_id}:dashboard_stats"
        cached_result = redis_manager.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Returning cached dashboard stats for professor {professor_id}")
            return DashboardStatsResponse(**cached_result)
        
        # Fetch from database
        logger.debug(f"Fetching dashboard stats from DB for professor {professor_id}")
        stats_dict = self.repository.get_dashboard_stats(professor_id)
        
        # Convert to response model
        response = DashboardStatsResponse(**stats_dict)
        
        # Cache for 5 minutes (300 seconds)
        redis_manager.set(cache_key, stats_dict, ttl=300)
        logger.debug(f"Cached dashboard stats for professor {professor_id}")
        
        return response
    
    def get_recent_activity(self, professor_id: int, limit: int = 10) -> List[ActivityItem]:
        """
        Get recent activity for professor dashboard.
        
        OPTIMIZATION: Uses Redis caching (2 min TTL) since activity changes frequently.
        """
        # Check cache first
        cache_key = f"professor:{professor_id}:recent_activity:limit={limit}"
        cached_result = redis_manager.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Returning cached recent activity for professor {professor_id}")
            return [ActivityItem(**item) for item in cached_result]
        
        # Fetch from database
        logger.debug(f"Fetching recent activity from DB for professor {professor_id}")
        activities_dict = self.repository.get_recent_activity(professor_id, limit)
        
        # Convert to response models
        activities = [ActivityItem(**item) for item in activities_dict]
        
        # Cache for 2 minutes (120 seconds) - activity changes frequently
        cache_data = [item.model_dump(mode='json') for item in activities]
        redis_manager.set(cache_key, cache_data, ttl=120)
        logger.debug(f"Cached recent activity for professor {professor_id}")
        
        return activities
