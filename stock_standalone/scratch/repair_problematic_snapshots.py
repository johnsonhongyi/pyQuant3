# -*- coding: utf-8 -*-
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bidding_momentum_detector import BiddingMomentumDetector
from JohnsonUtil import commonTips as cct
from scratch.restore_snapshots import parse_snapshot_info

def repair_snapshots():
    # 模拟配置初始化
    if not hasattr(cct, 'CFG'):
        class MockConfig:
            bidding_window_col = ['score', 'pct', 'score_diff']
            concept_top10_window_col = []
            duration_sleep_time = 120.0
        cct.CFG = MockConfig()
        
    snapshots_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'snapshots')
    snapshot_files = sorted([f for f in os.listdir(snapshots_dir) if re.match(r'^bidding_\d{8}\.json\.gz$', f)])
    
    repaired_count = 0
    
    for snap_file in snapshot_files:
        snap_path = os.path.join(snapshots_dir, snap_file)
        status, stocks, sectors = parse_snapshot_info(snap_path)
        
        is_corrupt = (status == "OK") and (sectors <= 1 and stocks > 1000)
        
        if is_corrupt:
            print(f"Repairing {snap_file} (Current sectors: {sectors}, Stocks: {stocks})...")
            
            # 1. Load the snapshot to trigger self-healing
            detector = BiddingMomentumDetector(simulation_mode=True, lazy_load=False)
            
            # Mock last data date & timestamp
            match = re.search(r'bidding_(\d{8})', snap_file)
            if match:
                date_str = match.group(1)
                detector._last_data_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
            
            success = detector.load_from_snapshot(snap_path)
            if not success or len(detector.active_sectors) == 0:
                print(f"  [FAILED] Could not self-heal {snap_file}")
                continue
                
            # 2. Redirect the persistence path to overwrite the snapshot file
            def mock_get_path(snapshot_date=None):
                return snap_path
                
            detector._get_persistence_path = mock_get_path
            detector.in_history_mode = False
            
            # Mock trade day to bypass non-trade-day write guards
            orig_status = cct.get_trade_date_status
            orig_istrade = cct.get_day_istrade_date
            cct.get_trade_date_status = lambda: True
            cct.get_day_istrade_date = lambda: True
            
            try:
                # Save the repaired snapshot back to disk
                detector.save_persistent_data(force=True)
            finally:
                # Restore original functions
                cct.get_trade_date_status = orig_status
                cct.get_day_istrade_date = orig_istrade
            
            # 3. Verify the repaired file
            v_status, v_stocks, v_sectors = parse_snapshot_info(snap_path)
            print(f"  [SUCCESS] Verified repaired {snap_file}: Stocks={v_stocks}, Sectors={v_sectors}, Status={v_status}")
            repaired_count += 1
            
    print("-" * 100)
    print(f"Repair completed. Repaired and rewrote {repaired_count} snapshot file(s).")

if __name__ == "__main__":
    repair_snapshots()
