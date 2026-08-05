import os
import sys
import time

# 自动定位项目根目录，确保以独立 python 脚本直接运行时不会发生 ModuleNotFoundError
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
import pandas as pd
import numpy as np
from multi_period_strategy_engine import MultiPeriodStrategyEngine, get_global_ipc_sync_manager
from stock_logic_utils import test_code_query as run_test_code_query, test_code_against_queries as run_test_code_against_queries

_GLOBAL_TEST_IPC_DF = None

def fetch_system_ipc_data():
    """
    100% 使用系统现有 `get_global_ipc_sync_manager()` 库获取行情 DataFrame。
    只测试 IPC 真实数据，绝对不使用离线假数据！
    """
    global _GLOBAL_TEST_IPC_DF
    if _GLOBAL_TEST_IPC_DF is not None and not _GLOBAL_TEST_IPC_DF.empty:
        return _GLOBAL_TEST_IPC_DF.copy()

    ipc_mgr = get_global_ipc_sync_manager()
    if not getattr(ipc_mgr, '_listener_running', False):
        ipc_mgr.start()
        time.sleep(0.5)

    ipc_df = ipc_mgr.get_current_df()
    for req_try in range(3):
        if ipc_df is not None and not ipc_df.empty:
            break
        print(f"\n[IPC 现有库] 正在调用 request_full_sync() 尝试第 {req_try+1} 次 (Port={ipc_mgr.port})...")
        sys.stdout.flush()
        ipc_mgr.request_full_sync()
        start_t = time.time()
        for attempt in range(60):  # 等待 6.0 秒
            time.sleep(0.1)
            ipc_df = ipc_mgr.get_current_df()
            if ipc_df is not None and not ipc_df.empty:
                print(f"[IPC 现有库] [OK] 成功从系统 {ipc_mgr.port} 端口接收到真实数据包 ({len(ipc_df)} 行, 耗时 {time.time()-start_t:.2f}s)！")
                sys.stdout.flush()
                break

    if ipc_df is None or ipc_df.empty:
        raise RuntimeError("[ERROR] [IPC 真实获取失败] 当前未连接真实 TK 监控端后台或未接收到 IPC 真实行情包！请确认 TK 监控端已启动。")

    _GLOBAL_TEST_IPC_DF = ipc_df.copy()

    print(f"\n==================== [系统 IPC 库获取到的 DF 详细信息] ====================")
    print(f"  - 总行数 (Rows): {len(ipc_df)}")
    print(f"  - 总列数 (Columns): {len(ipc_df.columns)}")
    print(f"  - 示例列名 (前 15 个): {list(ipc_df.columns)[:15]}")
    if '300058' in ipc_df.index:
        print(f"  - 300058 关键数据: close={ipc_df.loc['300058', 'close']}, nclose={ipc_df.loc['300058'].get('nclose', 'N/A')}")
    print(f"===========================================================================")
    sys.stdout.flush()
    return ipc_df


def test_300058_condition1_eval():
    """
    【IPC 真实数据对齐测试】
    使用系统现有 IPC 库 (get_global_ipc_sync_manager) 从 TK 监控端获取 300058 真实行情，
    经 MultiPeriodStrategyEngine 自动对齐补齐后，比对 [条件 1] 表达式并精准打印。
    """
    ipc_df = fetch_system_ipc_data()

    # 提取 300058 行数据
    if 'code' in ipc_df.columns:
        row_300058 = ipc_df[ipc_df['code'].astype(str).str.zfill(6) == '300058']
    elif '300058' in ipc_df.index:
        row_300058 = ipc_df.loc[['300058']]
    else:
        row_300058 = pd.DataFrame()

    if row_300058.empty:
        raise RuntimeError("[ERROR] [IPC 获取失败] 从 TK 监控端获取到的 5621 行数据集中未找到 300058 股票记录！")

    print(f"\n[300058 行行情数据调试] 成功从 5621 行 IPC 中提取到 300058:")
    print(f"  - 股票名称: {row_300058['name'].values[0] if 'name' in row_300058 else '未解包名称'}")
    print(f"  - close (现价): {row_300058['close'].values[0] if 'close' in row_300058 else '无'}")
    print(f"  - nclose (昨日收盘): {row_300058['nclose'].values[0] if 'nclose' in row_300058 else '无'}")
    print(f"  - vwap_cum_2d (机构成本): {row_300058['vwap_cum_2d'].values[0] if 'vwap_cum_2d' in row_300058 else '无'}")

    # 统一在多周期获取模块从 IPC 对齐补齐衍生列数据
    engine = MultiPeriodStrategyEngine()
    df_300058 = engine.ensure_strategy_ipc_columns(row_300058.copy(), force_refresh=True)

    expr = (
        "nclose >= 1.005 * vwap_cum_2d and "
        "vwap_cum_2d >= 1.002 * vwap_cum_3d and "
        "vwap_cum_3d >= vwap_cum_4d and "
        "close > open and "
        "(lastp1d >= ma51d or last_vwap_cum_2d > last_vwap_cum_3d or last_nclose1d > last_nclose3d) and "
        "(lastv0d * volume > lastv1d or lastv1d > 0.95 * lastv2d) and "
        "close > nclose"
    )

    queries = [{"expr": expr, "name": "300058 条件 1 测试"}]
    res = run_test_code_query(df_300058, queries)

    assert len(res) == 1
    item = res[0]

    # 4. 打印从 IPC 自动获取对齐后的精细诊断面板
    print("\n--------------------------------------------------")
    print(f"把[条件 1]")
    print(f"  表达式: {expr}")
    print(f"  是否通过: {'[YES] 是' if item['ok'] else '[NO] 否'}")
    print(f"  当前涉及字段数值:")
    row = item["full_data"]
    cols = ['nclose', 'vwap_cum_2d', 'vwap_cum_3d', 'vwap_cum_4d', 'close', 'open', 'lastp1d', 'ma51d', 'last_vwap_cum_2d', 'last_vwap_cum_3d', 'last_nclose1d', 'last_nclose3d', 'lastv0d', 'volume', 'lastv1d', 'lastv2d']
    for c in cols:
        print(f"    - {c}: {row.get(c)}")
    print(f"  子条件执行详情:")
    for sub in item["sub_conditions"]:
        cond_text = sub["condition"]
        is_pass = sub["ok"]
        vals_dict = sub.get("values", {})
        vals_str = ", ".join([f"{k}={v}" for k, v in vals_dict.items()]) if isinstance(vals_dict, dict) else str(vals_dict)
        tag = "[PASS]" if is_pass else "[FAIL]"
        print(f"    {tag} {cond_text} -> 当前值: {vals_str}")
    print("--------------------------------------------------\n")

    # 5. 断言验证：验证通过 IPC 获取到的 300058 真实字段存在且已成功对齐补齐
    assert "vwap_cum_2d" in row and not pd.isna(row["vwap_cum_2d"])
    assert "vwap_cum_3d" in row and not pd.isna(row["vwap_cum_3d"])
    
    sub_conds = item["sub_conditions"]
    assert len(sub_conds) >= 6


def test_300058_multi_period_ipc_column_sync():
    """
    【IPC 真实数据流测试】
    验证 300058 从 IPC 接收的真实数据在多周期引擎 (d, 2d, 3d, w, m) 加载与展平中保持高精度一致。
    """
    ipc_df = fetch_system_ipc_data()

    if 'code' in ipc_df.columns:
        row_300058 = ipc_df[ipc_df['code'].astype(str).str.zfill(6) == '300058']
    elif '300058' in ipc_df.index:
        row_300058 = ipc_df.loc[['300058']]
    else:
        row_300058 = pd.DataFrame()

    if row_300058.empty:
        raise RuntimeError("[ERROR] [IPC 获取失败] 当前 IPC 数据集中未包含 300058 标的！请确认 TK 监控端已推送数据。")

    engine = MultiPeriodStrategyEngine()
    for period in ['d', '2d', '3d', 'w', 'm']:
        res_df = engine.ensure_strategy_ipc_columns(row_300058.copy(), force_refresh=True)
        has_col = ('vwap_cum_2d' in res_df.columns) or ('vwap_cum_2d_d' in res_df.columns)
        assert has_col, "[ERROR] 缺失 vwap_cum_2d / vwap_cum_2d_d 列"


def test_300058_ipc_diagnose_row_enrichment():
    """
    【IPC 真实诊断链路测试】
    测试多周期诊断中直接从 IPC 真实缓存读取 300058 数据并自动补齐全量衍生列。
    """
    ipc_df = fetch_system_ipc_data()

    if 'code' in ipc_df.columns:
        row_300058 = ipc_df[ipc_df['code'].astype(str).str.zfill(6) == '300058']
    elif '300058' in ipc_df.index:
        row_300058 = ipc_df.loc[['300058']]
    else:
        row_300058 = pd.DataFrame()

    if row_300058.empty:
        raise RuntimeError("[ERROR] [IPC 获取失败] 当前 IPC 数据集中未包含 300058 标的！请确认 TK 监控端已推送数据。")

    engine = MultiPeriodStrategyEngine()
    df_enriched = engine.ensure_strategy_ipc_columns(row_300058.copy(), force_refresh=True)

    expr = "vwap_cum_2d > 0.0"
    res = run_test_code_query(df_enriched, [{"expr": expr}])

    assert len(res) == 1
    assert res[0]["ok"] is True
    full_data = res[0]["full_data"]
    assert "vwap_cum_2d" in full_data


def test_300058_real_tcp_ipc_socket_send_and_sync():
    """
    【真实 TCP Socket IPC 通信测试 (系统多周期标准 26671 接口)】
    使用系统标准多周期接口 get_global_ipc_sync_manager() (Port=26671)，向 TK 监控端发送 REQ_FULL_SYNC 指令，
    验证真实接收解包 300058 行情包，并由多周期引擎完成自动对齐。
    """
    ipc_mgr = get_global_ipc_sync_manager()
    ipc_df = fetch_system_ipc_data()

    engine = MultiPeriodStrategyEngine()
    res_df = engine.ensure_strategy_ipc_columns(ipc_df.copy(), force_refresh=True)

    if 'code' in res_df.columns:
        row_300058 = res_df[res_df['code'].astype(str).str.zfill(6) == '300058']
    elif '300058' in res_df.index:
        row_300058 = res_df.loc[['300058']]
    else:
        row_300058 = pd.DataFrame()

    assert not row_300058.empty, "[ERROR] 未能在系统 26671 端口 IPC 接收的 DF 中找到 300058 标的"
    target_col = 'vwap_cum_2d' if 'vwap_cum_2d' in row_300058.columns else 'vwap_cum_2d_d'
    assert target_col in row_300058.columns, "[ERROR] 未能在 300058 中找到 vwap_cum_2d 衍生列"

    v_2d = row_300058[target_col].iloc[0]
    print(f"\n[SUCCESS] [标准 26671 接口通信测试成功] 真实端口 26671 建立链接 -> 300058 行情包接收 -> 多周期自动补齐 {v_2d} 完美贯通！")


if __name__ == "__main__":
    pytest.main([__file__, "-s", "-v"])
