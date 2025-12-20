# -*- coding:utf-8 -*-
import sqlite3
import json
import traceback
from datetime import datetime
import numpy as np
import pandas as pd
from JohnsonUtil import inStockDb as inDb
from JohnsonUtil import LoggerFactory

# 获取或创建日志记录器
logger = LoggerFactory.getLogger("instock_TK.DB")

DB_PATH = "./concept_pg_data.db"

def get_indb_df(days=10):
    """从本地数据库获取最后几天的股票数据统计"""
    indf = inDb.showcount(inDb.selectlastDays(days), sort_date=True)
    if len(indf) == 0:
        indf = inDb.showcount(inDb.selectlastDays(days + 5), sort_date=True)
    return indf

def init_concept_db():
    """初始化概念数据 SQLite 数据库"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS concept_data (
            date TEXT,
            concept_name TEXT,
            init_data TEXT,
            prev_data TEXT,
            PRIMARY KEY (date, concept_name)
        )
    """)
    conn.commit()
    conn.close()

def save_concept_pg_data(win, concept_name):
    """保存每个概念当天数据到 SQLite，自动转换所有 NumPy 类型，并保留浮点数两位小数"""
    try:
        init_concept_db()
        date_str = datetime.now().strftime("%Y%m%d")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        def to_serializable(obj):
            """将 NumPy 类型自动转换为原生 Python 类型，并保留浮点数两位小数"""
            if isinstance(obj, np.ndarray):
                return [to_serializable(v) for v in obj.tolist()]
            elif isinstance(obj, (np.integer, np.int32, np.int64)):
                return int(obj)
            elif isinstance(obj, (np.floating, np.float32, np.float64, float)):
                return round(float(obj), 2)  # 保留两位小数
            elif isinstance(obj, dict):
                return {k: to_serializable(v) for k, v in obj.items()}
            elif isinstance(obj, (list, tuple)):
                return [to_serializable(v) for v in obj]
            else:
                return obj

        base_data = getattr(win, "_init_prev_concepts_data", {}).get(concept_name)
        prev_data = getattr(win, "_prev_concepts_data", {}).get(concept_name)
        if base_data is None:
            logger.info(f'[save_concept_pg_data] base_data is None for {concept_name}')
            conn.close()
            return

        init_serial = to_serializable(base_data)
        prev_serial = to_serializable(prev_data) if prev_data else {}

        cur.execute("""
            INSERT INTO concept_data (date, concept_name, init_data, prev_data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, concept_name)
            DO UPDATE SET
                init_data=excluded.init_data,
                prev_data=excluded.prev_data
        """, (
            date_str,
            concept_name,
            json.dumps(init_serial, ensure_ascii=False),
            json.dumps(prev_serial, ensure_ascii=False)
        ))

        conn.commit()
        conn.close()
        logger.info(f"[保存成功] {concept_name} 数据已写入 SQLite")
    except Exception as e:
        traceback.print_exc()
        logger.info(f"[保存失败] {concept_name} -> {e}")

def save_concept_pg_data_simple(win, concept_name):
    """保存每个概念当天数据到 SQLite（自动处理 ndarray -> list）"""
    try:
        init_concept_db()
        date_str = datetime.now().strftime("%Y%m%d")
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()

        # 将 ndarray 转为 list
        def arr_to_list(a):
            return a.tolist() if isinstance(a, np.ndarray) else a

        base_data = getattr(win, "_init_prev_concepts_data", {}).get(concept_name)
        prev_data = getattr(win, "_prev_concepts_data", {}).get(concept_name)

        if not base_data:
            logger.info(f"[保存失败] {concept_name} base_data is None")
            conn.close()
            return

        init_data = {
            "concepts": base_data["concepts"],
            "avg_percents": arr_to_list(base_data.get("avg_percents", [])),
            "scores": arr_to_list(base_data.get("scores", [])),
            "follow_ratios": arr_to_list(base_data.get("follow_ratios", [])),
        }
        prev_data_dict = {
            "concepts": prev_data.get("concepts", []) if prev_data else [],
            "avg_percents": arr_to_list(prev_data.get("avg_percents", [])) if prev_data else [],
            "scores": arr_to_list(prev_data.get("scores", [])) if prev_data else [],
            "follow_ratios": arr_to_list(prev_data.get("follow_ratios", [])) if prev_data else [],
        }

        cur.execute("""
            INSERT INTO concept_data (date, concept_name, init_data, prev_data)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, concept_name)
            DO UPDATE SET
                init_data=excluded.init_data,
                prev_data=excluded.prev_data
        """, (date_str, concept_name,
              json.dumps(init_data, ensure_ascii=False),
              json.dumps(prev_data_dict, ensure_ascii=False)))

        conn.commit()
        conn.close()
        logger.info(f"[保存成功] {concept_name} 数据已写入 SQLite")
    except Exception as e:
        traceback.print_exc()
        logger.info(f"[保存失败] {concept_name} -> {e}")

def load_concept_pg_data_no_serializable(concept_name):
    """加载当天概念数据"""
    date_str = datetime.now().strftime("%Y%m%d")
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT init_data, prev_data FROM concept_data WHERE date=? AND concept_name=?",
                    (date_str, concept_name))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None, None
        init_data = json.loads(row[0]) if row[0] else None
        prev_data = json.loads(row[1]) if row[1] else None
        return init_data, prev_data
    except Exception as e:
        logger.info(f"[加载失败] {concept_name} -> {e}")
        return None, None

def load_all_concepts_pg_data():
    """一次性加载当天所有概念数据"""
    date_str = datetime.now().strftime("%Y%m%d")
    result = {}
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT concept_name, init_data, prev_data FROM concept_data WHERE date=?", (date_str,))
        rows = cur.fetchall()
        conn.close()
        for concept_name, init_json, prev_json in rows:
            try:
                init_data = json.loads(init_json) if init_json else {}
                prev_data = json.loads(prev_json) if prev_json else {}
                for key in ["concepts", "avg_percents", "scores", "follow_ratios"]:
                    init_data.setdefault(key, [])
                    prev_data.setdefault(key, [])
                result[concept_name] = (init_data, prev_data)
            except Exception:
                logger.info(f"[加载单个概念失败] {concept_name}")
    except Exception as e:
        logger.info(f"[加载全部概念失败] {e}")
    return result
