# -*- coding: utf-8 -*-
"""
Stock Handbook Module
Manages stock remarks/notes storage using a simple JSON file.
"""
import os
import json
import time
from datetime import datetime
from JohnsonUtil import LoggerFactory

logger = LoggerFactory.getLogger()

class StockHandbook:
    def __init__(self, data_file="stock_handbook.json"):
        self.data_file = data_file
        self.data = self._load_data()

    def _load_data(self):
        """Load remarks from JSON file."""
        if not os.path.exists(self.data_file):
            return {}
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load handbook data: {e}")
            return {}

    def _save_data(self):
        """Save remarks to JSON file."""
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save handbook data: {e}")

    def add_remark(self, code, content):
        """
        Add a remark for a stock.
        
        Args:
            code (str): Stock code (e.g., "600519").
            content (str): The remark content.
        """
        timestamp = time.time()
        time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        
        if code not in self.data:
            self.data[code] = []
            
        entry = {
            "time": time_str,
            "timestamp": timestamp,
            "content": content
        }
        # Insert at the beginning (newest first)
        self.data[code].insert(0, entry)
        self._save_data()
        logger.info(f"Added remark for {code}")

    def get_remarks(self, code):
        """Get all remarks for a specific stock."""
        return self.data.get(code, [])

    def update_remark(self, code, timestamp, new_content):
        """
        Update remark content by timestamp.

        Args:
            code (str): Stock code.
            timestamp (float): Original timestamp of the remark.
            new_content (str): Updated content.
        """
        if code not in self.data:
            return False

        for r in self.data[code]:
            if r.get("timestamp") == timestamp:
                r["content"] = new_content
                self._save_data()
                logger.info(f"Updated remark for {code} at {timestamp}")
                return True

        return False

    # def delete_remark(self, code, timestamp):
    #     """Delete a specific remark by timestamp."""
    #     if code in self.data:
    #         initial_len = len(self.data[code])
    #         self.data[code] = [r for r in self.data[code] if r.get("timestamp") != timestamp]
    #         if len(self.data[code]) != initial_len:
    #             self._save_data()
    #             logger.info(f"Deleted remark for {code}")
    #         return True
    #     else:
    #         return False

    def delete_remark(self, code, timestamp):
        if code not in self.data:
            return False

        def normalize(ts):
            if isinstance(ts, str):
                return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()
            return float(ts)

        target_ts = normalize(timestamp)

        before = len(self.data[code])
        self.data[code] = [
            r for r in self.data[code]
            if abs(float(r.get("timestamp", 0)) - target_ts) > 1
        ]
        after = len(self.data[code])

        if after < before:
            self._save_data()
            return True

        return False


    def get_all_remarks(self):
        """Get all remarks (for searching)."""
        return self.data
