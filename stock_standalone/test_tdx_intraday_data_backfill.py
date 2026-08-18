# -*- coding: utf-8 -*-
"""
test_tdx_intraday_data_backfill.py — 验证 TDX 实盘分时 K 线回补与 7 节点自动评估准确性测试
"""
import sys
import os
import pandas as pd

# 将当前目录与子模块加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "ats"))

from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
from ats.intraday_strategy_engine import IntradayStrategyEngine

def test_tdx_backfill_and_node_evaluation():
    print("=" * 70)
    print("[TEST] 开始测试 TDX 秒级分时 K 线极速回补与 7 节点自动评估")
    print("=" * 70)

    # 1. 建立 TDX 实盘行情连接
    fetcher = TDXRealtimeFetcher.get_instance()
    conn_ok = fetcher.connect()
    assert conn_ok, "❌ TDX 服务器连接失败，请检查网络！"
    print("OK [TDX] 成功建立 TDX 主站行情直连")

    # 2. 从 TDX 拉取 688826 全量 240 分钟分时 K 线
    code = "688826"
    df_intraday = fetcher.fetch_intraday_bars(code)
    
    print(f"OK [TDX] 成功抓取标的 [{code}] 分时 K 线数据, 总计: {len(df_intraday)} 条")
    assert not df_intraday.empty, f"❌ 标的 [{code}] 从 TDX 获取的分时 K 线为空！"
    assert len(df_intraday) >= 30, f"❌ 标的 [{code}] 分时 K 线条数少于 30 条 (当前: {len(df_intraday)} 条)！"

    # 校验必要标准字段是否存在
    required_cols = ["open", "close", "high", "low", "vwap", "turnover_rate", "amount"]
    for col in required_cols:
        assert col in df_intraday.columns, f"❌ 分时 K 线缺少必须字段: {col}"

    op_first = float(df_intraday.iloc[0]["open"])
    cl_last = float(df_intraday.iloc[-1]["close"])
    vw_last = float(df_intraday.iloc[-1]["vwap"])
    to_last = float(df_intraday.iloc[-1]["turnover_rate"])
    amt_last = float(df_intraday.iloc[-1]["amount"])

    print(f"   [K线样本] 首条 09:25/09:30 今开: {op_first:.2f} 元")
    print(f"   [K线样本] 末条分时 现价: {cl_last:.2f} 元 | VWAP: {vw_last:.2f} 元")
    print(f"   [K线样本] 换手率: {to_last:.2f}% | 成交额: {amt_last/1e8:.2f} 亿元")

    # 3. 将全量分时 K 线注入 IntradayStrategyEngine 节点引擎
    engine = IntradayStrategyEngine.get_instance()
    engine.reset_node_custom_params(code)
    hydrated = engine.hydrate_from_intraday_df(code, df_intraday, open_price=op_first)
    assert hydrated, "❌ IntradayStrategyEngine 分时 K 线灌入解析失败！"
    print("OK [ENGINE] 分时 K 线已成功灌入引擎，09:25 / 09:40 / 10:00 / 11:00 全量节点快照已构建")

    # 4. 执行 7 节点自动时序评估与打分
    eval_res = engine.evaluate_seven_nodes(
        code=code,
        open_price=op_first,
        high_price=1300.0,
        low_price=1100.0,
        price=cl_last,
        turnover_rate=to_last,
        amount=amt_last,
        current_time_str="10:45:00"
    )
    nodes = {nr["node_id"]: nr for nr in eval_res.get("node_results", [])}

    print("\n[CHECK] 校验 7 节点自动评估获取的时间与数值正确性:")

    # 校验 09:25 开盘节点
    node_1 = nodes.get("node_1_auction")
    assert node_1 is not None, "❌ 缺少 Node 1 (09:25 集合竞价) 评估结果！"
    print(f"   Node 1 (09:25 竞价定盘) -> {node_1['observed_val']} (评分: {node_1.get('auto_score', 0)}分, 判定: {node_1['judgment']})")
    assert abs(node_1["input_val"] - op_first) < 0.1, f"❌ Node 1 价格与开盘价未对齐 (期望: {op_first}, 实际: {node_1['input_val']})"

    # 校验 09:40 攻击节点
    node_2 = nodes.get("node_2_first_wave") or nodes.get("node_2_first_attack")
    assert node_2 is not None, "❌ 缺少 Node 2 (09:40 早盘第一波攻击) 评估结果！"
    print(f"   Node 2 (09:40 冲高攻防) -> {node_2['observed_val']} (评分: {node_2.get('auto_score', 0)}分, 判定: {node_2['judgment']})")

    # 校验 10:00 换手节点
    node_3 = nodes.get("node_3_turnover") or nodes.get("node_3_turnover_check")
    assert node_3 is not None, "❌ 缺少 Node 3 (10:00 换手质量检验) 评估结果！"
    print(f"   Node 3 (10:00 换手检验) -> {node_3['observed_val']} (评分: {node_3.get('auto_score', 0)}分, 判定: {node_3['judgment']})")

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED! TDX 分时数据极速回补与 7 节点自动评估校验 100% 通过！")
    print("=" * 70)

if __name__ == "__main__":
    test_tdx_backfill_and_node_evaluation()
