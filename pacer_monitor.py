#!/usr/bin/env python3
"""
PACER Case Monitor - Federal Court Case Tracking System
Monitors up to 20-30 federal cases with cost optimization and notifications
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Set
import random
from dataclasses import dataclass, asdict
from pathlib import Path

# Third-party imports
import requests
from sqlalchemy import create_engine, Column, String, DateTime, Float, Integer, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import redis
from playwright.async_api import async_playwright
import juriscraper
from juriscraper.pacer import PacerSession

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

Base = declarative_base()

# Configuration
@dataclass
class Config:
    """Application configuration"""
    pacer_username: str = os.getenv('PACER_USERNAME', '')
    pacer_password: str = os.getenv('PACER_PASSWORD', '')
    courtlistener_token: str = os.getenv('COURTLISTENER_TOKEN', '')
    
    # Cost management
    quarterly_budget: float = 30.0  # $30 free tier
    cost_buffer: float = 5.0  # Stop at $25 to be safe
    
    # Polling intervals (seconds)
    high_priority_interval: int = 3600  # 1 hour
    medium_priority_interval: int = 21600  # 6 hours  
    low_priority_interval: int = 86400  # 24 hours
    
    # Database
    database_url: str = os.getenv('DATABASE_URL', 'sqlite:///pacer_monitor.db')
    redis_url: str = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Notifications
    webhook_url: Optional[str] = os.getenv('WEBHOOK_URL')
    email_notifications: bool = os.getenv('EMAIL_NOTIFICATIONS', 'false').lower() == 'true'
    
    # PACER settings
    pacer_poll_hours: tuple = (18, 6)  # 6 PM to 6 AM Central
    max_retries: int = 3
    retry_delay: int = 60

# Database Models
class Case(Base):
    __tablename__ = 'cases'
    
    case_number = Column(String, primary_key=True)
    court_id = Column(String, nullable=False)
    case_name = Column(String)
    priority = Column(String, default='medium')  # high, medium, low
    last_checked = Column(DateTime)
    last_updated = Column(DateTime)
    docket_entries_count = Column(Integer, default=0)
    notification_enabled = Column(Boolean, default=True)
    metadata = Column(Text)  # JSON field for additional data

class CostTracking(Base):
    __tablename__ = 'cost_tracking'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, default=datetime.utcnow)
    case_number = Column(String)
    action = Column(String)  # docket_check, document_download
    pages = Column(Integer)
    cost = Column(Float)
    quarter = Column(String)  # YYYY-Q#

class DocketEntry(Base):
    __tablename__ = 'docket_entries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    case_number = Column(String, index=True)
    entry_number = Column(Integer)
    date_filed = Column(DateTime)
    description = Column(Text)
    document_url = Column(String)
    first_seen = Column(DateTime, default=datetime.utcnow)

class CaseMonitor:
    """Main monitoring application"""
    
    def __init__(self, config: Config):
        self.config = config
        self.engine = create_engine(config.database_url)
        Base.metadata.create_all(self.engine)
        Session = sessionmaker(bind=self.engine)
        self.db = Session()
        
        # Initialize Redis for caching
        self.redis_client = redis.from_url(config.redis_url, decode_responses=True)
        
        # Initialize PACER session
        self.pacer_session = None
        self.courtlistener_session = requests.Session()
        if config.courtlistener_token:
            self.courtlistener_session.headers.update({
                'Authorization': f'Token {config.courtlistener_token}'
            })
    
    async def initialize_pacer(self):
        """Initialize PACER session with Juriscraper"""
        try:
            self.pacer_session = PacerSession(
                username=self.config.pacer_username,
                password=self.config.pacer_password
            )
            self.pacer_session.login()
            logger.info("Successfully logged into PACER")
        except Exception as e:
            logger.error(f"Failed to initialize PACER session: {e}")
            raise
    
    def add_case(self, case_number: str, court_id: str, priority: str = 'medium'):
        """Add a new case to monitor"""
        existing = self.db.query(Case).filter_by(case_number=case_number).first()
        if existing:
            logger.info(f"Case {case_number} already exists, updating priority")
            existing.priority = priority
        else:
            new_case = Case(
                case_number=case_number,
                court_id=court_id,
                priority=priority,
                metadata=json.dumps({})
            )
            self.db.add(new_case)
        self.db.commit()
        logger.info(f"Added case {case_number} with priority {priority}")
    
    def get_current_quarter_cost(self) -> float:
        """Calculate total cost for current quarter"""
        now = datetime.utcnow()
        quarter = f"{now.year}-Q{(now.month-1)//3 + 1}"
        
        result = self.db.query(
            CostTracking
        ).filter(
            CostTracking.quarter == quarter
        ).with_entities(
            CostTracking.cost
        ).all()
        
        return sum(cost[0] for cost in result)
    
    def can_afford_query(self, estimated_pages: int = 3) -> bool:
        """Check if we can afford a query without exceeding budget"""
        current_cost = self.get_current_quarter_cost()
        estimated_cost = estimated_pages * 0.10
        
        return (current_cost + estimated_cost) < (self.config.quarterly_budget - self.config.cost_buffer)
    
    def record_cost(self, case_number: str, action: str, pages: int, cost: float):
        """Record cost for tracking"""
        now = datetime.utcnow()
        quarter = f"{now.year}-Q{(now.month-1)//3 + 1}"
        
        entry = CostTracking(
            case_number=case_number,
            action=action,
            pages=pages,
            cost=cost,
            quarter=quarter
        )
        self.db.add(entry)
        self.db.commit()
    
    async def check_courtlistener_first(self, case_number: str, court_id: str) -> Optional[Dict]:
        """Check CourtListener/RECAP for free data before hitting PACER"""
        cache_key = f"courtlistener:{court_id}:{case_number}"
        cached = self.redis_client.get(cache_key)
        
        if cached:
            return json.loads(cached)
        
        try:
            # Search for docket in CourtListener
            response = self.courtlistener_session.get(
                'https://www.courtlistener.com/api/rest/v4/dockets/',
                params={
                    'court': court_id,
                    'docket_number': case_number
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('results'):
                    docket = data['results'][0]
                    # Cache for 1 hour
                    self.redis_client.setex(
                        cache_key, 
                        3600, 
                        json.dumps(docket)
                    )
                    return docket
        except Exception as e:
            logger.warning(f"CourtListener check failed: {e}")
        
        return None
    
    async def check_case_with_playwright(self, case: Case) -> List[Dict]:
        """Use Playwright for cases requiring browser automation"""
        new_entries = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                # Navigate to PACER
                await page.goto(f'https://ecf.{case.court_id}.uscourts.gov')
                
                # Login if needed
                if await page.is_visible('input[name="login"]'):
                    await page.fill('input[name="login"]', self.config.pacer_username)
                    await page.fill('input[name="key"]', self.config.pacer_password)
                    await page.click('input[type="submit"]')
                    await page.wait_for_load_state('networkidle')
                
                # Search for case
                await page.goto(f'https://ecf.{case.court_id}.uscourts.gov/cgi-bin/DktRpt.pl')
                await page.fill('input[name="case_num"]', case.case_number)
                await page.click('input[value="Run Report"]')
                await page.wait_for_load_state('networkidle')
                
                # Parse docket entries
                entries = await page.query_selector_all('tr.docket-entry')
                
                for entry in entries:
                    entry_data = await self.parse_docket_entry(page, entry)
                    if entry_data:
                        new_entries.append(entry_data)
                
                # Record cost (estimate based on page count)
                pages = len(await page.query_selector_all('.page-break')) or 1
                cost = min(pages * 0.10, 3.00)  # Max $3 per document
                self.record_cost(case.case_number, 'docket_check', pages, cost)
                
            except Exception as e:
                logger.error(f"Error checking case {case.case_number}: {e}")
            finally:
                await browser.close()
        
        return new_entries
    
    async def parse_docket_entry(self, page, entry_element) -> Optional[Dict]:
        """Parse a single docket entry"""
        try:
            entry_number = await entry_element.query_selector('.entry-number')
            date_filed = await entry_element.query_selector('.date-filed')
            description = await entry_element.query_selector('.docket-text')
            
            if all([entry_number, date_filed, description]):
                return {
                    'entry_number': await entry_number.inner_text(),
                    'date_filed': await date_filed.inner_text(),
                    'description': await description.inner_text()
                }
        except Exception as e:
            logger.warning(f"Error parsing docket entry: {e}")
        
        return None
    
    def should_check_case(self, case: Case) -> bool:
        """Determine if a case should be checked based on priority and timing"""
        if not case.last_checked:
            return True
        
        intervals = {
            'high': self.config.high_priority_interval,
            'medium': self.config.medium_priority_interval,
            'low': self.config.low_priority_interval
        }
        
        interval = intervals.get(case.priority, self.config.medium_priority_interval)
        # Add jitter to prevent thundering herd
        interval = interval * (1 + random.uniform(-0.1, 0.1))
        
        return datetime.utcnow() - case.last_checked > timedelta(seconds=interval)
    
    async def send_notification(self, case: Case, new_entries: List[Dict]):
        """Send notifications for new docket entries"""
        if not case.notification_enabled or not new_entries:
            return
        
        message = {
            'case_number': case.case_number,
            'case_name': case.case_name,
            'court_id': case.court_id,
            'new_entries': new_entries,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Webhook notification
        if self.config.webhook_url:
            try:
                response = requests.post(
                    self.config.webhook_url,
                    json=message,
                    timeout=10
                )
                response.raise_for_status()
                logger.info(f"Sent webhook notification for {case.case_number}")
            except Exception as e:
                logger.error(f"Failed to send webhook: {e}")
        
        # Additional notification methods can be added here
        # (email, SMS, push notifications, etc.)
    
    async def monitor_single_case(self, case: Case):
        """Monitor a single case for updates"""
        if not self.should_check_case(case):
            return
        
        if not self.can_afford_query():
            logger.warning(f"Approaching budget limit, skipping {case.case_number}")
            return
        
        try:
            # First check CourtListener for free data
            courtlistener_data = await self.check_courtlistener_first(
                case.case_number, 
                case.court_id
            )
            
            if courtlistener_data:
                logger.info(f"Found {case.case_number} in CourtListener, using free data")
                # Process CourtListener data
                # ... (implementation depends on data structure)
            else:
                # Fall back to PACER
                new_entries = await self.check_case_with_playwright(case)
                
                if new_entries:
                    # Store new entries
                    for entry in new_entries:
                        existing = self.db.query(DocketEntry).filter_by(
                            case_number=case.case_number,
                            entry_number=entry['entry_number']
                        ).first()
                        
                        if not existing:
                            docket_entry = DocketEntry(
                                case_number=case.case_number,
                                **entry
                            )
                            self.db.add(docket_entry)
                    
                    self.db.commit()
                    
                    # Send notifications
                    await self.send_notification(case, new_entries)
            
            # Update last checked time
            case.last_checked = datetime.utcnow()
            self.db.commit()
            
        except Exception as e:
            logger.error(f"Error monitoring case {case.case_number}: {e}")
    
    async def run_monitoring_cycle(self):
        """Run a complete monitoring cycle for all cases"""
        cases = self.db.query(Case).all()
        logger.info(f"Starting monitoring cycle for {len(cases)} cases")
        
        # Check if we're in allowed hours (6 PM - 6 AM Central)
        current_hour = datetime.utcnow().hour
        if not (self.config.pacer_poll_hours[0] <= current_hour or 
                current_hour <= self.config.pacer_poll_hours[1]):
            logger.info("Outside of recommended PACER polling hours")
        
        # Process cases concurrently but with limits
        semaphore = asyncio.Semaphore(3)  # Max 3 concurrent checks
        
        async def check_with_limit(case):
            async with semaphore:
                await self.monitor_single_case(case)
        
        tasks = [check_with_limit(case) for case in cases]
        await asyncio.gather(*tasks)
        
        # Log cost status
        current_cost = self.get_current_quarter_cost()
        logger.info(f"Current quarter cost: ${current_cost:.2f} / ${self.config.quarterly_budget}")
    
    async def run(self):
        """Main run loop"""
        logger.info("Starting PACER Case Monitor")
        
        # Initialize PACER session
        await self.initialize_pacer()
        
        while True:
            try:
                await self.run_monitoring_cycle()
                
                # Sleep until next cycle
                await asyncio.sleep(300)  # 5 minutes
                
            except KeyboardInterrupt:
                logger.info("Received shutdown signal")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                await asyncio.sleep(60)  # Wait before retrying

# CLI Interface
def main():
    """Command line interface"""
    import argparse
    
    parser = argparse.ArgumentParser(description='PACER Case Monitor')
    parser.add_argument('command', choices=['run', 'add', 'list', 'costs'])
    parser.add_argument('--case-number', help='Case number to add')
    parser.add_argument('--court-id', help='Court ID (e.g., nysd, cacd)')
    parser.add_argument('--priority', choices=['high', 'medium', 'low'], default='medium')
    
    args = parser.parse_args()
    
    config = Config()
    monitor = CaseMonitor(config)
    
    if args.command == 'run':
        asyncio.run(monitor.run())
    
    elif args.command == 'add':
        if not args.case_number or not args.court_id:
            print("Error: --case-number and --court-id required for add command")
            return
        
        monitor.add_case(args.case_number, args.court_id, args.priority)
        print(f"Added case {args.case_number} to monitoring")
    
    elif args.command == 'list':
        cases = monitor.db.query(Case).all()
        print(f"\nMonitoring {len(cases)} cases:")
        for case in cases:
            print(f"  {case.case_number} ({case.court_id}) - Priority: {case.priority}")
    
    elif args.command == 'costs':
        current_cost = monitor.get_current_quarter_cost()
        print(f"\nCurrent quarter cost: ${current_cost:.2f}")
        print(f"Remaining budget: ${config.quarterly_budget - current_cost:.2f}")

if __name__ == '__main__':
    main()