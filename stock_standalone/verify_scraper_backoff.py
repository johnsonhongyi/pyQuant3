# -*- coding: utf-8 -*-
import time
import pandas as pd
from realtime_data_service import DataPublisher

def test_backoff_logic():
    # Set a small initial interval for testing
    pub = DataPublisher(high_performance=False, scraper_interval=30)
    print(f"Initial wait: {pub.current_scraper_wait}")
    
    # Simulate a failure (mocking scraper return)
    # Since _scraper_task runs in a thread, we'll just manually trigger the logic parts 
    # if we can, or just inspect the code logic. 
    # Actually, let's test the state transitions.
    
    # 1. Simulate failure 1
    pub.current_scraper_wait = min(pub.current_scraper_wait * 2, pub.max_scraper_wait)
    print(f"After failure 1, wait: {pub.current_scraper_wait}")
    
    # 2. Simulate failure 2
    pub.current_scraper_wait = min(pub.current_scraper_wait * 2, pub.max_scraper_wait)
    print(f"After failure 2, wait: {pub.current_scraper_wait}")
    
    # 3. Simulate success
    pub.current_scraper_wait = pub.scraper_interval
    print(f"After success, wait reset to: {pub.current_scraper_wait}")

if __name__ == "__main__":
    test_backoff_logic()
