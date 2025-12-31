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
        Add or update a remark for a stock.
        If the same code already has a remark on the same day, overwrite it.
        
        Args:
            code (str): Stock code (e.g., "600519").
            content (str): The remark content.
        """
        timestamp = time.time()
        time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")

        if code not in self.data:
            self.data[code] = []

        # 查找是否已存在同一天的记录
        for entry in self.data[code]:
            if entry.get("time") == time_str:
                # 覆盖内容与时间戳
                entry["content"] = content
                entry["timestamp"] = timestamp
                self._save_data()
                logger.info(f"Updated remark for {code} on {time_str}")
                return

        # 不存在则新增（插入到最前，最新在前）
        entry = {
            "time": time_str,
            "timestamp": timestamp,
            "content": content
        }
        self.data[code].insert(0, entry)
        self._save_data()
        logger.info(f"Added remark for {code}")

    # def add_remark(self, code, content):
    #     """
    #     Add a remark for a stock.
        
    #     Args:
    #         code (str): Stock code (e.g., "600519").
    #         content (str): The remark content.
    #     """
    #     timestamp = time.time()
    #     # time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    #     time_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        
    #     if code not in self.data:
    #         self.data[code] = []
            
    #     entry = {
    #         "time": time_str,
    #         "timestamp": timestamp,
    #         "content": content
    #     }
    #     # Insert at the beginning (newest first)
    #     self.data[code].insert(0, entry)
    #     self._save_data()
    #     logger.info(f"Added remark for {code}")

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

    # def delete_remark(self, code, timestamp):
    #     if code not in self.data:
    #         return False

    #     def normalize(ts):
    #         if isinstance(ts, str):
    #             # return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").timestamp()
    #             return datetime.strptime(ts, "%Y-%m-%d").timestamp()
    #         return float(ts)

    #     target_ts = normalize(timestamp)

    #     before = len(self.data[code])
    #     self.data[code] = [
    #         r for r in self.data[code]
    #         if abs(float(r.get("timestamp", 0)) - target_ts) > 1
    #     ]
    #     after = len(self.data[code])

    #     if after < before:
    #         self._save_data()
    #         return True

    #     return False

    def delete_remark(self, code, day):
        """
        Delete remark by code + day (YYYY-MM-DD),
        compatible with old time formats.
        """
        if code not in self.data:
            return False

        # 统一成 YYYY-MM-DD
        if isinstance(day, str):
            day_str = day[:10]
        else:
            day_str = datetime.fromtimestamp(float(day)).strftime("%Y-%m-%d")

        before = len(self.data[code])

        self.data[code] = [
            r for r in self.data[code]
            if r.get("time", "")[:10] != day_str
        ]

        after = len(self.data[code])

        if after < before:
            self._save_data()
            return True

        return False


    def get_all_remarks(self):
        """Get all remarks (for searching)."""
        return self.data
