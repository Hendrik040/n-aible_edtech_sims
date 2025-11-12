#!/usr/bin/env python3
"""
Monitor database connection pool in real-time

Usage:
    python scripts/monitor_pool.py
    python scripts/monitor_pool.py --interval 2  # Check every 2 seconds
"""

import sys
import time
import argparse
from pathlib import Path
from datetime import datetime

# Add backend to path
sys.path.append(str(Path(__file__).parent.parent))

from database.connection import engine

def get_pool_stats():
    """Get current connection pool statistics"""
    if not engine or not hasattr(engine, 'pool'):
        return None
    
    pool = engine.pool
    
    try:
        stats = {
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "invalid": pool.invalid(),
            "total_connections": pool.size() + pool.overflow(),
        }
        
        # Calculate utilization
        max_connections = pool.size() + (pool._max_overflow if hasattr(pool, '_max_overflow') else pool.max_overflow if hasattr(pool, 'max_overflow') else 0)
        stats["utilization_percent"] = round((stats["checked_out"] / max_connections * 100), 2) if max_connections > 0 else 0
        stats["max_connections"] = max_connections
        
        return stats
    except Exception as e:
        return {"error": str(e)}

def monitor_pool(interval: int = 5, duration: int = None):
    """Monitor connection pool continuously"""
    print("🔍 Database Connection Pool Monitor")
    print("=" * 60)
    print(f"Checking every {interval} seconds")
    if duration:
        print(f"Duration: {duration} seconds")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()
    
    start_time = time.time()
    max_utilization = 0
    
    try:
        while True:
            if duration and (time.time() - start_time) > duration:
                break
            
            stats = get_pool_stats()
            if stats and "error" not in stats:
                timestamp = datetime.now().strftime("%H:%M:%S")
                utilization = stats["utilization_percent"]
                
                # Track max utilization
                if utilization > max_utilization:
                    max_utilization = utilization
                
                # Color code based on utilization
                status = "🟢" if utilization < 50 else "🟡" if utilization < 80 else "🔴"
                
                print(f"[{timestamp}] {status} Pool: {stats['checked_out']}/{stats['max_connections']} "
                      f"({utilization}%) | "
                      f"Available: {stats['checked_in']} | "
                      f"Overflow: {stats['overflow']}")
                
                if utilization > 80:
                    print(f"   ⚠️  WARNING: High pool utilization!")
            else:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error getting pool stats: {stats.get('error', 'Unknown')}")
            
            time.sleep(interval)
    
    except KeyboardInterrupt:
        print("\n\n📊 Monitoring stopped")
        print(f"   Max utilization: {max_utilization}%")
        print("=" * 60)

def main():
    parser = argparse.ArgumentParser(description="Monitor database connection pool")
    parser.add_argument("--interval", type=int, default=5, help="Check interval in seconds")
    parser.add_argument("--duration", type=int, default=None, help="Monitor duration in seconds")
    
    args = parser.parse_args()
    
    monitor_pool(args.interval, args.duration)

if __name__ == "__main__":
    main()

