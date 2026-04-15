"""
Scanner Scheduler
Runs the accumulation scanner at a specific time on weekdays OR continuously every 15 minutes

PRD Multi-Timeframe Scheduler:
- 15m scan → every 5 min
- 4H scan → every 30 min
- 1D scan → every 2 hours
"""

import logging
import asyncio
from datetime import datetime
from typing import Callable, Optional
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.executors.pool import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class ScannerScheduler:
    """
    Scheduler for running the scanner:
    - Daily at specific time on weekdays (default 3:00 PM IST)
    - OR continuous every 15 minutes with signal publishing
    
    PRD Multi-Timeframe Support:
    - 15m timeframe scans: every 5 minutes
    - 4h timeframe scans: every 30 minutes  
    - 1d timeframe scans: every 2 hours
    """
    
    # PRD Scan intervals
    PRD_SCAN_INTERVALS = {
        "15m": 5,      # 15m scan → every 5 min
        "1h": 5,       # 1h scan → every 5 min
        "4h": 30,      # 4h scan → every 30 min
        "daily": 120   # 1d scan → every 2 hours
    }
    
    def __init__(self, config: dict):
        self.config = config
        self.scheduler_config = config.get('scheduler', {})
        
        self.timezone = self.scheduler_config.get('timezone', 'Asia/Kolkata')
        
        self.scan_hour = self.scheduler_config.get('scan_time_hour', 15)
        self.scan_minute = self.scheduler_config.get('scan_time_minute', 0)
        
        self.run_days = self.scheduler_config.get('run_days', [1, 2, 3, 4, 5])
        
        self.run_mode = self.scheduler_config.get('run_mode', 'continuous')
        
        executors = {
            'default': ThreadPoolExecutor(max_workers=4)
        }
        
        self.scheduler = BackgroundScheduler(
            executors=executors,
            timezone=self.timezone
        )
        
        self.job = None
        self.monitor_job = None
        
        # PRD: Multi-timeframe scan jobs
        self.mtf_jobs = {}
        
        self._signal_publisher = None
    
    def set_signal_publisher(self, publisher):
        """Set the signal publisher for monitoring."""
        self._signal_publisher = publisher
    
    def add_job(self, func: Callable, job_id: str = 'scanner_job') -> None:
        """
        Add the scanner job to the scheduler.
        Based on run_mode: 'continuous' for 15-min scans, 'scheduled' for daily scan.
        """
        if self.run_mode == 'continuous':
            scan_interval = self.scheduler_config.get('continuous_interval_minutes', 15)
            
            trigger = IntervalTrigger(
                minutes=scan_interval,
                timezone=self.timezone
            )
            
            self.job = self.scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                name=f'Continuous Scanner (Every {scan_interval} minutes)',
                replace_existing=True
            )
            
            logger.info(f"Continuous scan job scheduled: every {scan_interval} minutes")
            
            self._add_monitoring_job()
            
        else:
            trigger = CronTrigger(
                hour=self.scan_hour,
                minute=self.scan_minute,
                day_of_week=self.run_days,
                timezone=self.timezone
            )
            
            self.job = self.scheduler.add_job(
                func,
                trigger=trigger,
                id=job_id,
                name=f'Daily Scanner (at {self.scan_hour}:{self.scan_minute:02d} IST)',
                replace_existing=True
            )
            
            logger.info(f"Daily scan job scheduled: {self.scan_hour}:{self.scan_minute:02d} IST on days {self.run_days}")
            
            self._add_monitoring_job()
    
    def add_mtf_scan_job(self, func: Callable, timeframe: str, job_id: str = None) -> None:
        """
        Add a multi-timeframe scan job based on PRD intervals.
        
        PRD Intervals:
        - 15m scan → every 5 min
        - 4H scan → every 30 min
        - 1D scan → every 2 hours
        """
        interval_minutes = self.PRD_SCAN_INTERVALS.get(timeframe, 15)
        
        if job_id is None:
            job_id = f'scan_{timeframe}'
        
        trigger = IntervalTrigger(
            minutes=interval_minutes,
            timezone=self.timezone
        )
        
        self.mtf_jobs[timeframe] = self.scheduler.add_job(
            func,
            trigger=trigger,
            id=job_id,
            name=f'Scan {timeframe} (Every {interval_minutes} min)',
            replace_existing=True
        )
        
        logger.info(f"Added MTF scan job for {timeframe}: every {interval_minutes} minutes")
    
    def _add_monitoring_job(self):
        """Add the signal monitoring job to check SL/TP every 15 minutes."""
        sie_config = self.config.get('signal_intelligence', {})
        monitor_interval = sie_config.get('monitoring', {}).get('check_interval_minutes', 15)
        
        def monitor_func():
            if self._signal_publisher:
                logger.info("Running signal resolution monitoring...")
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        resolved = loop.run_until_complete(
                            self._signal_publisher.check_signals_resolution()
                        )
                        if resolved:
                            logger.info(f"Resolved {len(resolved)} signals")
                    finally:
                        loop.close()
                except Exception as e:
                    logger.error(f"Error in signal monitoring: {e}")
        
        trigger = IntervalTrigger(
            minutes=monitor_interval,
            timezone=self.timezone
        )
        
        self.monitor_job = self.scheduler.add_job(
            monitor_func,
            trigger=trigger,
            id='signal_monitor_job',
            name='Signal SL/TP Monitor',
            replace_existing=True
        )
        
        logger.info(f"Signal monitoring job scheduled: every {monitor_interval} minutes")
    
    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
            
            if self.run_mode == 'continuous':
                logger.info(f"Scheduler started - continuous scanning every {self.scheduler_config.get('continuous_interval_minutes', 15)} minutes")
            else:
                logger.info(f"Scheduler started - daily scan at {self.scan_hour}:{self.scan_minute:02d} IST on Mon-Fri")
    
    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Scheduler stopped")
    
    def get_next_run(self) -> Optional[datetime]:
        if self.job:
            return self.job.next_run_time
        return None
    
    def get_status(self) -> dict:
        return {
            'running': self.scheduler.running,
            'next_run': self.get_next_run(),
            'job_id': self.job.id if self.job else None,
            'scan_time': f'{self.scan_hour}:{self.scan_minute:02d}' if self.run_mode != 'continuous' else f'every {self.scheduler_config.get("continuous_interval_minutes", 15)} min',
            'run_days': self.run_days,
            'run_mode': self.run_mode
        }
    
    def add_monitor_job(self, func: Callable, job_id: str = 'monitor_job') -> None:
        """Add a signal monitoring job - deprecated, use _add_monitoring_job instead"""
        pass


def create_scheduler(config: dict, signal_publisher=None) -> ScannerScheduler:
    """
    Factory function to create and configure a ScannerScheduler instance.
    
    Args:
        config: Configuration dictionary with scheduler settings
        signal_publisher: Optional signal publisher for monitoring
        
    Returns:
        Configured ScannerScheduler instance
    """
    scheduler = ScannerScheduler(config)
    if signal_publisher:
        scheduler.set_signal_publisher(signal_publisher)
    return scheduler
