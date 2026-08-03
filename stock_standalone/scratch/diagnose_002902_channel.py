# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 解决 Windows CMD/PowerShell GBK 编码输出 Emoji UnicodeEncodeError 问题
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import re
import pandas as pd
from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df

def print_channel_strategy_plan(code_str, last, high_date, low_date, tc2, bc2, nod):
    close_p = float(last['close'])
    upper_p = float(last['ch_upper'])
    mid_p = float(last['ch_mid'])
    lower_p = float(last['ch_lower'])
    slope = float(last['ch_slope'])
    slope_deg = float(last['ch_slope_deg'])
    pos = float(last['ch_pos'])
    pattern = int(last['ch_pattern'])

    # 1. 判定多空方向与趋势阶段
    if pos > 100.0:
        bias_str = "🔥 强多头 (上轨突破浪)"
        bias_action = "【做多 - 突破加速单】"
        buy_plan = f"① 回踩上轨支撑 [{upper_p:.2f} 元] 企稳做多；② 盘中封板强行追击单。"
        target_plan = f"暂不设上限，上轨突破后空间打开，目标查看前高 [{last['ch_anchor_high_price']:.2f} 元]。"
        stop_plan = f"第一防守位看上轨 [{upper_p:.2f} 元]，若有效跌回上轨下方 2% ({upper_p * 0.98:.2f} 元) 离场保本。"
        flow_diagram = f"""   ┌──────────────────────────────────────────────────────────┐
   │ 当前股价 {close_p:.2f}元 > 上轨 {upper_p:.2f}元 (ch_pos = {pos:.1f}%)        │
   └────────────────────────────┬─────────────────────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
【买入】回踩上轨 {upper_p:.2f}元 企稳低吸         【防守】跌破 {upper_p * 0.98:.2f}元 止损离场"""
    elif pattern == 1 and pos >= 50.0:
        bias_str = "🟢 多头控盘 (中轨上方上升通道)"
        bias_action = "【做多 - 中轨低吸 / 持股观望】"
        buy_plan = f"回踩中轨 [{mid_p:.2f} 元] ~ [{mid_p * 1.02:.2f} 元] 附近缩量企稳分批建仓做多。"
        target_plan = f"第一目标上看通道上轨 [{upper_p:.2f} 元] (距当前空间 +{(upper_p/close_p-1)*100:.1f}%)。"
        stop_plan = f"防守止损位设在中轨下方 2% ({mid_p * 0.98:.2f} 元)，收盘跌破止损。"
        flow_diagram = f"""   ┌──────────────────────────────────────────────────────────┐
   │ 当前股价 {close_p:.2f}元 站稳中轨 {mid_p:.2f}元 (ch_pos = {pos:.1f}%)         │
   └────────────────────────────┬─────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
【买入】回踩中轨 {mid_p:.2f}元企稳  【目标】看向上轨 {upper_p:.2f}元  【止损】跌破 {mid_p*0.98:.2f}元止损"""
    elif pattern == 1 and pos < 50.0:
        bias_str = "🟡 多头蓄势 (低位企稳筑底)"
        bias_action = "【做多 - 试错超跌 / 突破中轨跟进】"
        buy_plan = f"① 贴近下轨 [{lower_p:.2f} 元] 企稳小仓试错；② 放量站上中轨 [{mid_p:.2f} 元] 加仓做多。"
        target_plan = f"第一目标看中轨 [{mid_p:.2f} 元]，第二目标看向上轨 [{upper_p:.2f} 元]。"
        stop_plan = f"下轨支撑 [{lower_p:.2f} 元] 为最终防守位，创新低 ({lower_p * 0.98:.2f} 元) 坚决止损。"
        flow_diagram = f"""   ┌──────────────────────────────────────────────────────────┐
   │ 当前股价 {close_p:.2f}元 在下轨与中轨间筑底 (ch_pos = {pos:.1f}%)       │
   └────────────────────────────┬─────────────────────────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          ▼                     ▼                     ▼
【买入】下轨 {lower_p:.2f}元企稳试错 【目标】看向中轨 {mid_p:.2f}元  【止损】跌破 {lower_p*0.98:.2f}元止损"""
    else:
        bias_str = "🔴 空头占优 (触顶回落 / 阴跌通道)"
        bias_action = "【观望 - 离场避险 / 待地量超跌】"
        buy_plan = f"多头力量偏弱，暂时观望；仅在回落至下轨 [{lower_p:.2f} 元] 极度地量时考虑极轻仓超跌反弹。"
        target_plan = f"反弹第一目标仅看中轨 [{mid_p:.2f} 元]，逢高分批减仓。"
        stop_plan = f"防守价 [{lower_p:.2f} 元]，破位无条件清仓。"
        flow_diagram = f"""   ┌──────────────────────────────────────────────────────────┐
   │ 当前趋势触顶回落 (ch_pattern = -1, ch_pos = {pos:.1f}%)               │
   └────────────────────────────┬─────────────────────────────┘
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
【观望】空头通道严禁盲目抄底             【防守】跌破下轨 {lower_p:.2f}元 离场避险"""

    print(f"=== 🎯 自动通道实战策略计划与操作指引 ===")
    print(f"1. 多空方向: {bias_str} -> 推荐动作: {bias_action}")
    print(f"2. 做多买入计划: {buy_plan}")
    print(f"3. 目标止盈计划: {target_plan}")
    print(f"4. 止损防守计划: {stop_plan}")
    print(f"5. 策略路线图:")
    print(flow_diagram)
    print("=" * 60 + "\n")

def diagnose_stock_channel(code_str="002902"):
    # 自动正则提取 6 位数字代码
    digit_match = re.search(r'\d{6}', str(code_str))
    code_str = digit_match.group(0) if digit_match else "002902"

    # 1. 读取数据 (get_tdx_Exp_day_to_df 内部已算好全套通道指标)
    df = get_tdx_Exp_day_to_df(code_str)
    if df is None or len(df) == 0:
        print(f"❌ 错误：无法获取股票 [{code_str}] 的日线数据。")
        return

    # 2. 直接读取最新一天的数据切片 (df.iloc[-1])
    last = df.iloc[-1]
    n = len(df)

    tc2 = int(last['ch_tc2'])
    bc2 = int(last['ch_bc2'])
    nod = int(last['ch_nod'])
    high_date = df.index[max(0, n - tc2)]
    low_date = df.index[max(0, n - bc2)]

    # 先显示基础诊断信息
    print(f"\n==================================================")
    print(f"=== 股票【{code_str}】自动通道极值诊断 (读取最新切片数据) ===")
    print(f"==================================================")
    print(f"最新交易日: {df.index[-1]}, 最新收盘价: {last['close']:.2f} 元")
    print(f"通道三轨: 上轨 (ch_upper) = {last['ch_upper']:.2f} 元, 中轨 (ch_mid) = {last['ch_mid']:.2f} 元, 下轨 (ch_lower) = {last['ch_lower']:.2f} 元")
    print(f"通道斜率: {last['ch_slope']:.4f} (倾角 {last['ch_slope_deg']:.2f}°), 价格相对位置 (ch_pos): {last['ch_pos']:.2f}%")
    print(f"顶点日期: {high_date}, 顶点最高价: {last['ch_anchor_high_price']:.2f} 元, 距今 (tc2): {tc2} 根")
    print(f"底点日期: {low_date}, 底点最低价: {last['ch_anchor_low_price']:.2f} 元, 距今 (bc2): {bc2} 根")
    print(f"高低点间隔 (nod): {nod} 根, 趋势格局 (ch_pattern): {int(last['ch_pattern'])} ({'触底走高' if last['ch_pattern'] == 1 else '触顶走低'})\n")

    # 随后打印通道实战策略计划与操作路线图
    print_channel_strategy_plan(code_str, last, high_date, low_date, tc2, bc2, nod)

    # 3. 输出最近 10 天特征明细表
    cols = [
        'close', 'ch_upper', 'ch_mid', 'ch_lower', 'ch_slope', 'ch_slope_deg', 'ch_pos',
        'ch_anchor_high_price', 'ch_anchor_low_price', 'ch_tc2', 'ch_bc2', 'ch_nod', 'ch_pattern'
    ]
    pd.set_option('display.max_columns', 20)
    pd.set_option('display.width', 1000)
    print(f"=== 最近 10 个交易日【{code_str}】通道与极值特征明细表 ===")
    print(df[cols].tail(10))

if __name__ == "__main__":
    target_code = sys.argv[1] if len(sys.argv) > 1 else input("请输入 6 位股票代码 (回车默认 002902): ").strip() or "002902"
    diagnose_stock_channel(target_code)
