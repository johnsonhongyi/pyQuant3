# -*- coding: utf-8 -*-
"""
repair_voice_prices.py

工具脚本：使用历史数据回补语音预警中缺失的“加入时价格 (create_price)”。
逻辑：
1. 读取 voice_alert_config.json 配置文件。
2. 匹配需要使用创建日期的 YYYY-MM-DD 部分作为索引在历史数据中查找价格。
3. 使用 tdd.get_tdx_Exp_day_to_df 获取历史数据。
4. 更新 JSON 及数据库中的 create_price 和 created_time。
"""

import os
import json
import logging
from datetime import datetime
import pandas as pd

# 导入项目模块
from JSONData import tdx_data_Day as tdd
from JohnsonUtil import commonTips as cct
from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import LoggerFactory
from trading_logger import TradingLogger

# 配置日志
logger = LoggerFactory.getLogger(name="repair_prices")

def repair():
    db_path = "./trading_signals.db"
    config_file = "./voice_alert_config.json"
    
    tl = TradingLogger(db_path)
    logger.info("Starting price repair process...")
    
    if not os.path.exists(config_file):
        logger.error(f"Config file {config_file} not found")
        return

    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            monitors_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {config_file}: {e}")
        return

    updated_count = 0

    for key, data in monitors_data.items():
        # key 可能是 "600000" 或 "600000_d"
        code = key.split('_')[0]
        resample = data.get('resample', 'd')
        create_price = data.get('create_price', 0)
        created_time_str = data.get('created_time', '')
        name = data.get('name', '')
        
        # 如果已有或者没有时间，跳过
        if create_price > 0:
            continue
            
        if not created_time_str:
            logger.warning(f"Skipping {code} ({name}): No created_time found")
            continue
            
        logger.info(f"Repairing {code} ({name}) added at {created_time_str}...")
        
        try:
            # 解析时间
            # 兼容多种格式: 2026-01-26 20:15:07 或 2026-01-26 20:15 或 2026-01-26 11
            dt_obj = None
            date_formats = ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d %H', '%Y-%m-%d']
            for fmt in date_formats:
                try:
                    dt_obj = datetime.strptime(created_time_str, fmt)
                    break
                except ValueError:
                    continue
            
            if not dt_obj:
                logger.error(f"Could not parse created_time: {created_time_str}")
                continue

            # 使用日期部分匹配
            target_date = dt_obj.strftime('%Y-%m-%d')
            
            # 获取历史数据
            dl = ct.Resample_LABELS_Days.get(resample, 200)
            df_hist = tdd.get_tdx_Exp_day_to_df(code, dl=dl, resample=resample, fastohlc=True)
            
            if df_hist is None or df_hist.empty:
                logger.error(f"Failed to fetch history for {code}")
                continue
                
            found_price = 0.0
            # 索引匹配
            if target_date in df_hist.index:
                row = df_hist.loc[target_date]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                found_price = float(row.get('close', 0))
            else:
                # 模糊匹配：找小于等于 target_date 的最后一天
                past_df = df_hist[df_hist.index <= target_date]
                if not past_df.empty:
                    found_price = float(past_df.iloc[-1].get('close', 0))
                else:
                    found_price = float(df_hist.iloc[0].get('open', 0))

            if found_price > 0:
                print(f"✅ Found price for {code} ({name}): {found_price:.2f} on {target_date}")
                logger.info(f"Successfully repaired {code}: {found_price:.2f} (Date: {target_date})")
                
                # 更新内存中的 JSON 数据
                data['create_price'] = found_price
                
                # 同步到数据库
                tl.log_voice_alert_config(
                    code=code,
                    resample=resample,
                    name=name,
                    rules=json.dumps(data.get('rules', [])),
                    last_alert=data.get('last_alert', 0),
                    tags=data.get('tags', ''),
                    rule_type_tag=data.get('rule_type_tag', ''),
                    create_price=found_price,
                    created_time=created_time_str # 保持原始时间字符串
                )
                
                updated_count += 1
            else:
                print(f"❌ Price not found for {code} ({name}) on {target_date}")
                logger.warning(f"Price not found for {code} on {target_date}")

        except Exception as e:
            logger.error(f"Error processing {code}: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # 保存 JSON
    if updated_count > 0:
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(monitors_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Updated {config_file} with {updated_count} repaired prices.")
            print(f"Successfully updated {updated_count} items.")
        except Exception as e:
            logger.error(f"Failed to save {config_file}: {e}")

    logger.info("Repair process finished.")

if __name__ == "__main__":
    repair()
