# -*- coding: utf-8 -*-
import os
import zlib
import gzip
import json
import shutil
import re

def parse_snapshot_info(filepath):
    """尝试加载快照并获取核心指标"""
    stocks = 0
    sectors = 0
    status = "OK"
    try:
        with open(filepath, 'rb') as f:
            raw = f.read()
        try:
            json_str = zlib.decompress(raw).decode('utf-8')
        except Exception:
            json_str = gzip.decompress(raw).decode('utf-8')
        data = json.loads(json_str)
        stocks = len(data.get('stock_scores', {}))
        sectors = len(data.get('sector_data', {}))
    except Exception as e:
        status = f"ERROR: {str(e)[:30]}"
    return status, stocks, sectors

def restore_snapshots():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    snapshots_dir = os.path.join(base_dir, 'snapshots')
    backup_dir = os.path.join(snapshots_dir, 'backup')
    
    if not os.path.exists(snapshots_dir):
        print("Snapshots directory does not exist.")
        return
        
    # 1. 扫描所有备份文件并提取指标
    backups = []
    if os.path.exists(backup_dir):
        for f in os.listdir(backup_dir):
            if f.endswith('.gz'):
                filepath = os.path.join(backup_dir, f)
                size_kb = os.path.getsize(filepath) / 1024
                match = re.search(r'bak_(\d{8})_\d{6}', f)
                if match:
                    date_str = match.group(1)
                    status, stocks, sectors = parse_snapshot_info(filepath)
                    backups.append({
                        'filename': f,
                        'filepath': filepath,
                        'date': date_str,
                        'size_kb': size_kb,
                        'status': status,
                        'stocks': stocks,
                        'sectors': sectors
                    })
    
    print(f"Loaded {len(backups)} backups from {backup_dir}")
    for b in backups:
        print(f"  Backup: {b['filename']} | Date: {b['date']} | Size: {b['size_kb']:.1f}KB | Status: {b['status']} | Stocks: {b['stocks']} | Sectors: {b['sectors']}")
    print("-" * 100)

    # 2. 扫描所有 bidding_YYYYMMDD.json.gz 日常快照并诊断
    snapshot_files = sorted([f for f in os.listdir(snapshots_dir) if re.match(r'^bidding_\d{8}\.json\.gz$', f)])
    
    restored_count = 0
    
    for snap_file in snapshot_files:
        snap_path = os.path.join(snapshots_dir, snap_file)
        date_str = snap_file.replace('bidding_', '').replace('.json.gz', '')
        size_kb = os.path.getsize(snap_path) / 1024
        
        status, stocks, sectors = parse_snapshot_info(snap_path)
        
        # 判断该日常快照是否有问题
        is_problematic = (status != "OK") or (sectors <= 1 and stocks > 1000)
        
        if is_problematic:
            print(f"\n[ALERT] Detect problematic snapshot: {snap_file} (Size: {size_kb:.1f}KB, Stocks: {stocks}, Sectors: {sectors}, Status: {status})")
            
            # 在备份中寻找这一天数据最完整的备份
            candidates = [b for b in backups if b['date'] == date_str and b['status'] == "OK" and b['sectors'] > sectors]
            
            if candidates:
                # 按照板块数量最多、大小最大的顺序排序
                candidates.sort(key=lambda x: (x['sectors'], x['size_kb']), reverse=True)
                best_backup = candidates[0]
                
                print(f"  -> Found better backup: {best_backup['filename']} (Sectors: {best_backup['sectors']}, Size: {best_backup['size_kb']:.1f}KB)")
                
                # 执行备份恢复
                try:
                    # 先备份有问题的原文件
                    corrupt_bak = snap_path + ".corrupt"
                    if os.path.exists(snap_path):
                        os.rename(snap_path, corrupt_bak)
                    
                    shutil.copy2(best_backup['filepath'], snap_path)
                    print(f"  [SUCCESS] Restored {snap_file} from backup {best_backup['filename']}")
                    restored_count += 1
                    
                    # 验证恢复后的文件
                    v_status, v_stocks, v_sectors = parse_snapshot_info(snap_path)
                    print(f"     Verified restored file: Stocks={v_stocks}, Sectors={v_sectors}, Status={v_status}")
                    
                    # 删除临时的 .corrupt 备份
                    if os.path.exists(corrupt_bak):
                        os.remove(corrupt_bak)
                except Exception as e:
                    print(f"  [FAILED] Failed to restore {snap_file}: {e}")
            else:
                print(f"  -> [FAILED] No better backup found in backup folder for date {date_str}.")
                
    print("-" * 100)
    print(f"Restoration completed. Restored {restored_count} snapshot file(s).")

if __name__ == "__main__":
    restore_snapshots()
