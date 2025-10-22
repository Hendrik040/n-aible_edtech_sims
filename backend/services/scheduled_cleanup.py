"""
Scheduled Cleanup Service
Automatically cleans up old archived records on a schedule
"""

import schedule
import time
from datetime import datetime, date
from services.soft_deletion import SoftDeletionService
from database.connection import get_db


class ScheduledCleanupService:
    """Service for scheduled cleanup of archived records"""
    
    def __init__(self):
        self.cleanup_days = 30  # Default: clean archives older than 30 days
    
    def set_cleanup_days(self, days: int):
        """Set the number of days after which to clean up archives"""
        self.cleanup_days = days
    
    def run_cleanup(self):
        """Run the cleanup process"""
        
        db_gen = get_db()
        try:
            db = next(db_gen)
            service = SoftDeletionService(db)
            
            # Get stats before cleanup
            stats_before = service.get_archive_stats()
            
            # Run cleanup
            cleaned_count = service.cleanup_old_archives(self.cleanup_days)
            
            # Get stats after cleanup
            stats_after = service.get_archive_stats()
            
        except Exception as e:
        finally:
            try:
                next(db_gen)  # Trigger the finally block in get_db()
            except StopIteration:
                pass
    
    def monthly_cleanup_wrapper(self):
        """Wrapper that checks if it's the 1st of the month before running cleanup"""
        if date.today().day == 1:
            self.run_cleanup()
        else:
    
    def start_daily_cleanup(self):
        """Start daily cleanup at 2 AM"""
        schedule.every().day.at("02:00").do(self.run_cleanup)
    
    def start_weekly_cleanup(self):
        """Start weekly cleanup on Sundays at 2 AM"""
        schedule.every().sunday.at("02:00").do(self.run_cleanup)
    
    def start_monthly_cleanup(self):
        """Start monthly cleanup on the 1st at 2 AM"""
        schedule.every().day.at("02:00").do(self.monthly_cleanup_wrapper)
    
    def run_scheduler(self):
        """Run the scheduler (blocking)"""
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
        except KeyboardInterrupt:


def main():
    """Main function for running scheduled cleanup"""
    cleanup_service = ScheduledCleanupService()
    
    # Set cleanup to 30 days (archives older than 30 days)
    cleanup_service.set_cleanup_days(30)
    
    # Schedule daily cleanup
    cleanup_service.start_daily_cleanup()
    
    # Run the scheduler
    cleanup_service.run_scheduler()


if __name__ == "__main__":
    main()
