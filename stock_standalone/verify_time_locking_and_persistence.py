# -*- coding: utf-8 -*-
"""
verify_time_locking_and_persistence.py — 验证分时策略7节点按时间严格锁定、磁盘持久化缓存、开盘价同步及最低价异常修复
"""
import sys
import os
import shutil
import json
from datetime import datetime

# 确保 Windows 控制台编码安全
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

# 确保定位到项目根目录
_CUR_DIR = os.path.dirname(os.path.abspath(__file__))
if _CUR_DIR not in sys.path:
    sys.path.insert(0, _CUR_DIR)

from ats.intraday_strategy_engine import IntradayStrategyEngine
from ats.tdx_realtime_fetcher import TDXRealtimeFetcher


def run_verification():
    print("=" * 70)
    print("[TEST] 开始验证分时策略7节点按时间严格锁定、持久化缓存与开盘价对齐")
    print("=" * 70)

    engine = IntradayStrategyEngine.get_instance()
    code = "688826"
    
    # 0. 清理现有测试缓存与定盘账本
    cache_file = engine._get_cache_filepath()
    if os.path.exists(cache_file):
        os.remove(cache_file)
    closing_file = engine._get_closing_eval_filepath()
    if os.path.exists(closing_file):
        os.remove(closing_file)
    engine.rule_state_map.clear()

    open_p = 1100.00

    # 1. 模拟 09:25 集合竞价行情
    res_0925 = engine.evaluate_seven_nodes(
        code=code,
        current_time_str="09:25:00",
        open_price=open_p,
        price=open_p,
        high_price=open_p,
        low_price=open_p,
        vwap=open_p,
        turnover_rate=0.0,
        amount=0.0
    )
    print("OK [09:25:00] 开盘价已锁死为:", open_p)

    # 2. 模拟 09:40 节点行情 (现价 1199.58)
    price_0940 = 1199.58
    res_0940 = engine.evaluate_seven_nodes(
        code=code,
        current_time_str="09:40:00",
        open_price=open_p,
        price=price_0940,
        high_price=1250.00,
        low_price=1100.00,
        vwap=1140.00,
        turnover_rate=15.0,
        amount=200000000.0
    )
    print("OK [09:40:00] 节点2 (09:40早盘第一波攻击) 现价为:", price_0940)

    # 3. 模拟 10:00 节点行情 (换手率 61.39%, 现价 1221.00)
    to_1000 = 61.39
    price_1000 = 1221.00
    res_1000 = engine.evaluate_seven_nodes(
        code=code,
        current_time_str="10:00:00",
        open_price=open_p,
        price=price_1000,
        high_price=1300.00,
        low_price=1100.00,
        vwap=1149.79,
        turnover_rate=to_1000,
        amount=874000000.0
    )
    print("OK [10:00:00] 节点3 (10:00换手质量检验) 换手率为:", to_1000)

    # 4. 模拟 10:45:00 实时行情变动 (价格跳涨到 1280.00, 换手率上升到 75.0%)
    res_1045 = engine.evaluate_seven_nodes(
        code=code,
        current_time_str="10:45:00",
        open_price=open_p,
        price=1280.00,
        high_price=1300.00,
        low_price=1.00, # 故意传入 1.00 噪声 low_price 验证过滤
        vwap=1160.00,
        turnover_rate=75.0,
        amount=950000000.0
    )

    # 验证 10:45 时，节点 2 (09:40 现价) 和 节点 3 (10:00 换手率) 是否被严格时间锁定！
    nodes = res_1045["node_results"]
    node2_input = nodes[1]["input_val"] # 09:40 现价
    node3_input = nodes[2]["input_val"] # 10:00 换手率
    min_p_res = res_1045["low_price"]

    print("\n[CHECK] 检查 [10:45:00] 时节点参数是否严格锁定:")
    print(f"   Node 2 (09:40 攻击现价) 锁定值: {node2_input:.2f}元 (预期: {price_0940:.2f}元)")
    print(f"   Node 3 (10:00 换手率)   锁定值: {node3_input:.2f}%  (预期: {to_1000:.2f}%)")
    print(f"   SBC 最低价过滤结果:     {min_p_res:.2f}元 (预期: 1100.00元, 已成功过滤 1.00元)")

    assert abs(node2_input - price_0940) < 0.01, f"Node 2 价格锁定失败! {node2_input} vs {price_0940}"
    assert abs(node3_input - to_1000) < 0.01, f"Node 3 换手率锁定失败! {node3_input} vs {to_1000}"
    assert min_p_res > 1.0, f"最低价过滤失败, 仍然包含 1.00! {min_p_res}"
    print("[PASS] 7节点评估已实现严格按时间锁死，且成功过滤 1.00元 最低价噪声！")

    # 5. 验证开盘价对齐与规则挂单计算 (rule_pz_halt_30 临停 +30% 阈值: 1100*1.30=1430.00, 挂单 1.28x = 1408.00)
    tick_row = {"trade": 1450.00, "close": 1450.00, "vwap": 1149.79, "turnover": 61.39, "amount": 874000000.0}
    sigs = engine.evaluate_tick(
        code=code,
        tick_row=tick_row,
        open_price=open_p,
        current_time_str="09:59:00",
        bid1_price=1450.00
    )
    state = engine._get_stock_state(code, open_p)
    print("\n[CHECK] 检查规则触发日志与阈值对齐:")
    for log in state["execution_logs"]:
        print("   LOG:", log)

    assert any("临停阈值:1430.00" in log for log in state["execution_logs"]), "规则临停阈值未能对齐开盘价 1100*1.30=1430.00!"
    assert any("建议挂单:1408.00" in log for log in state["execution_logs"]), "规则建议挂单价未能对齐开盘价 1100*1.28=1408.00!"
    print("[PASS] 规则触发阈值与建议挂单价已 100% 对齐最新开盘价！")

    # 6. 验证持久化缓存文件写入与崩溃重启还原
    print("\n[CHECK] 检查磁盘持久化缓存文件:", cache_file)
    assert os.path.exists(cache_file), f"持久化缓存文件未生成: {cache_file}"

    # 模拟崩溃/重启: 清空内存 rule_state_map 并重新从磁盘加载
    engine.rule_state_map.clear()
    assert len(engine.rule_state_map) == 0
    loaded_ok = engine.load_intraday_cache()
    assert loaded_ok, "重启从磁盘加载缓存失败!"

    state_restored = engine.rule_state_map.get(code)
    assert state_restored is not None, "标的状态还原失败!"
    print("   还原开盘价:", state_restored["open_price"])
    print("   还原触发规则:", state_restored["triggered_rules"])
    print("   还原锁死节点:", state_restored["node_locked_params"])

    assert abs(state_restored["open_price"] - open_p) < 0.01, "还原开盘价不匹配!"
    assert "rule_pz_halt_30" in state_restored["triggered_rules"], "还原触发规则不匹配!"
    assert "node_2" in state_restored["node_locked_params"], "还原锁定节点不匹配!"
    print("[PASS] 磁盘持久化缓存还原成功，崩溃重启后状态与锁死节点 100% 保持无缝一致！")

    # 7. 验证中途/午后启动时通过分时 DataFrame 全量恢复早盘节点 (hydrate_from_intraday_df)
    print("\n[CHECK] 检查分时 K 线 / DataFrame 全量恢复早盘节点:")
    engine.rule_state_map.clear()
    import pandas as pd
    mock_df_data = [
        {"time": "09:30:00", "open": 1100.0, "close": 1120.0, "high": 1130.0, "low": 1100.0, "turnover": 5.0, "amount": 50000000.0},
        {"time": "09:40:00", "open": 1150.0, "close": 1199.58, "high": 1210.0, "low": 1140.0, "turnover": 18.0, "amount": 200000000.0},
        {"time": "10:00:00", "open": 1200.0, "close": 1221.0, "high": 1300.0, "low": 1180.0, "turnover": 61.39, "amount": 874000000.0},
        {"time": "11:00:00", "open": 1210.0, "close": 1182.24, "high": 1230.0, "low": 1170.0, "turnover": 65.50, "amount": 920000000.0}
    ]
    df_mock = pd.DataFrame(mock_df_data)
    df_mock.set_index("time", inplace=True)

    hydrated = engine.hydrate_from_intraday_df(code, df_mock, open_price=1100.00)
    assert hydrated, "分时 DataFrame 回溯充能失败!"

    state_hydrated = engine._get_stock_state(code, 1100.00)
    locked = state_hydrated["node_locked_params"]
    print("   全量恢复开盘价 (node_1):", locked.get("node_1"))
    print("   全量恢复09:40现价 (node_2):", locked.get("node_2"))
    print("   全量恢复10:00换手 (node_3):", locked.get("node_3"))
    print("   全量恢复11:00现价 (node_4):", locked.get("node_4"))

    assert abs(locked.get("node_1", 0.0) - 1100.00) < 0.01, f"node_1 恢复失败: {locked.get('node_1')}"
    assert abs(locked.get("node_2", 0.0) - 1199.58) < 0.01, f"node_2 恢复失败: {locked.get('node_2')}"
    assert abs(locked.get("node_3", 0.0) - 61.39) < 0.01, f"node_3 恢复失败: {locked.get('node_3')}"
    assert abs(locked.get("node_4", 0.0) - 1182.24) < 0.01, f"node_4 恢复失败: {locked.get('node_4')}"
    print("[PASS] 早盘全量历史节点已通过分时 K 线成功精准恢复，彻底解决中途/午后启动丢失早盘数据的问题！")

    # 8. 验证存在旧的残余缓存 (如 560.64/616.70) 时，新开盘价 1100.00 + K线 能强力清洗覆盖并重新锁定
    print("\n[CHECK] 检查陈旧错乱缓存 (如 560.64 元) 的自动清洗与强力对齐:")
    state_stale = engine._get_stock_state(code, 1100.00)
    state_stale["node_locked_params"]["node_1"] = 560.64 # 注入旧的陈旧锁死值
    state_stale["node_locked_params"]["node_2"] = 616.70
    engine.save_intraday_cache()

    # 模拟 UI 强力回溯充能
    engine.hydrate_from_intraday_df(code, df_mock, open_price=1100.00)

    state_fixed = engine._get_stock_state(code, 1100.00)
    locked_fixed = state_fixed["node_locked_params"]
    print("   清洗后开盘价 (node_1):", locked_fixed.get("node_1"))
    print("   清洗后09:40现价 (node_2):", locked_fixed.get("node_2"))
    assert abs(locked_fixed.get("node_1", 0.0) - 1100.00) < 0.01, f"陈旧缓存清洗失败, node_1: {locked_fixed.get('node_1')}"
    assert abs(locked_fixed.get("node_2", 0.0) - 1199.58) < 0.01, f"陈旧缓存清洗失败, node_2: {locked_fixed.get('node_2')}"
    print("[PASS] 成功清洗陈旧 560.64 元残留缓存，节点1与节点2已 100% 强力对齐最新真实开盘价与分时 K 线！")

    # 9. 验证脏数据落盘防污染、15:00收盘定盘评分保存与上市次日(T+1)自动切通用普通股策略
    print("\n[CHECK] 检查脏数据防落盘污染、首日收盘评分保存与 T+1 自动切通用普通股策略:")
    
    # 9a. 脏数据防落盘校验
    dirty_code = "999999"
    engine._get_stock_state(dirty_code, 0.0) # 无效 open_price = 0.0
    engine.save_intraday_cache()
    
    with open(cache_file, "r", encoding="utf-8") as f:
        cache_content = json.load(f)
    assert dirty_code not in cache_content.get("stocks", {}), "❌ 脏数据(op<=1.0)被误写入磁盘缓存!"
    print("   [9a PASS] 脏数据防污染规则生效，未连线/无效行情标的未被写入磁盘缓存！")

    # 9b. 首日 15:00 收盘评分保存校验
    res_close = engine.evaluate_seven_nodes(
        code=code,
        current_time_str="15:00:00",
        open_price=1100.00,
        price=1186.00,
        high_price=1300.00,
        low_price=1100.00,
        vwap=1182.24,
        turnover_rate=65.50,
        amount=5899000000.0
    )
    closing_scorecards = engine.load_listing_closing_scorecards()
    assert code in closing_scorecards, "❌ 15:00 首日收盘定盘综合评分未持久化至 newstock_listing_closing_evaluations.json!"
    c_rec = closing_scorecards[code]
    print(f"   [9b PASS] 15:00 收盘定盘评分成功持久化: {c_rec.get('total_weighted_score')}分, 形态: {c_rec.get('pattern')}")

    # 9c. 次日 T+1 自动切通用普通股策略校验
    c_rec["date"] = "2026-08-17" # 模拟历史首日记录 (昨天)
    fp_close = engine._get_closing_eval_filepath()
    with open(fp_close, "w", encoding="utf-8") as f:
        json.dump(closing_scorecards, f, ensure_ascii=False, indent=2)

    t1_strat = engine.auto_select_strategy(1100.00, code=code)
    print("   [9c PASS] 次日(T+1)自动切换策略名称:", t1_strat.get("name"))
    assert t1_strat.get("id") == "strategy_c_daily_surge_ladder", f"❌ 次日未能自动切换为通用普通股策略: {t1_strat.get('id')}"
    print("[PASS] 上市首日收盘评分持久化与次日(T+1)自动切通用普通股策略全部验证通过！")

    # 测试完成后清理临时测试缓存，防止污染真实实盘环境
    try:
        if os.path.exists(cache_file):
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({}, f)
    except Exception:
        pass

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED! 所有功能校验通过！")
    print("=" * 70)


if __name__ == "__main__":
    run_verification()
