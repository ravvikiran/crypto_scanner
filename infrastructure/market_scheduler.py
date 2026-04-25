"""
Market Scheduler for Crypto Scanner (24/7 Operation)
Crypto markets are always open. No market hours restrictions.
"""

import os
import logging
from datetime import datetime, timedelta, time as dt_time
from typing import Optional, List
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import get_config
from loguru import logger

logger = logging.getLogger(__name__)


class MarketScheduler:
    """
    Scheduler for 24/7 cryptocurrency markets.
    
    Unlike traditional stock markets, crypto markets never close.
    This scheduler:
    - Always reports market as OPEN
    - Supports configurable scan intervals
    - No weekend/holiday restrictions
    - No timezone-specific market hours
    """
    
    def __init__(self, config=None):
        self.config = config or get_config()
        self.scheduler = BackgroundScheduler()
        self.run_mode = self._get_run_mode()
        self._setup_scheduler()
        logger.info("MarketScheduler initialized for 24/7 crypto markets")
    
    def _get_run_mode(self) -> str:
        """Determine scheduler run mode from config."""
        mode = os.environ.get('SCANNER_MODE', 'continuous')
        return mode
    
    def _setup_scheduler(self):
        """Configure scheduler jobs based on mode."""
        try:
            # Get scan interval from config
            interval_minutes = getattr(self.config.scanner, 'scan_interval_minutes', 15)
            
            # Add main scan job - runs every X minutes, 24/7
            trigger = IntervalTrigger(minutes=interval_minutes)
            
            self.scheduler.add_job(
                self._scan_job_wrapper,
                trigger,
                id='main_scan',
                name=f'Crypto Scan (every {interval_minutes} min)',
                replace_existing=True
            )
            
            logger.info(f"Scheduler configured: {self.run_mode} mode, interval={interval_minutes}min")
        except Exception as e:
            logger.error(f"Scheduler setup error: {e}")
            raise
    
    def _scan_job_wrapper(self):
        """Wrapper for scan job execution."""
        try:
            logger.info(f"Starting scheduled scan at {datetime.now().isoformat()}")
            # The actual scan will be triggered by the main loop
            # This just logs that it's time
        except Exception as e:
            logger.error(f"Scan job error: {e}")
    
    def start(self):
        """Start the scheduler."""
        try:
            self.scheduler.start()
            logger.info("Scheduler started - 24/7 operation")
        except Exception as e:
            logger.error(f"Failed to start scheduler: {e}")
            raise
    
    def stop(self):
        """Stop the scheduler."""
        try:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
    def get_next_run(self) -> Optional[str]:
        """Get next scheduled run time."""
        try:
            job = self.scheduler.get_job('main_scan')
            if job:
                next_run = job.next_run_time
                return next_run.isoformat() if next_run else None
        except Exception as e:
            logger.error(f"Error getting next run: {e}")
        return None
    
    def get_market_status(self) -> str:
        """
        Get current market status.
        For crypto, always OPEN.
        """
        return "OPEN"
    
    def is_market_open(self) -> bool:
        """
        Check if market is open.
        For crypto, always True.
        """
        return True
    
    def is_market_hours(self) -> bool:
        """
        Check if current time is within market hours.
        For crypto, always True.
        """
        return True
    
    def get_time_until_market_open(self) -> Optional[float]:
        """
        Get seconds until market opens.
        For crypto, always 0.
        """
        return 0.0
    
    def get_time_until_market_close(self) -> Optional[float]:
        """
        Get seconds until market closes.
        For crypto, returns None (never closes).
        """
        return None
    
    def get_next_market_open(self) -> Optional[str]:
        """
        Get next market open time.
        For crypto, returns current time.
        """
        return datetime.now().isoformat()
    
    def add_job(self, func, *args, **kwargs):
        """Add a job to the scheduler."""
        self.scheduler.add_job(func, *args, **kwargs)
    
    def remove_job(self, job_id: str):
        """Remove a job from the scheduler."""
        try:
            self.scheduler.remove_job(job_id)
        except Exception as e:
            logger.error(f"Error removing job {job_id}: {e}")
    
    @property
    def jobs(self) -> List:
        """Get all scheduled jobs."""
        return self.scheduler.get_jobs()
