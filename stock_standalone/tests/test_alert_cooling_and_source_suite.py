# -*- coding: utf-8 -*-
"""
test_alert_cooling_and_source_suite.py — 针对 AlertNotifier 10分钟单股冷却防重、新异动即时放行与来源标记的系统性自动化测试
"""

import sys
import os
import time
import pytest
from PyQt6.QtWidgets import QApplication

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ats.alert_notifier import AlertNotifier


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


def test_alert_cooling_and_source_attribution(qapp):
    """测试报警来源明确标识、10分钟单股冷却防重与新异动即时放行机制"""
    notifier = AlertNotifier.get_instance()
    notifier.set_voice_enabled(False) # 测试中关闭真实发声
    notifier.set_toast_enabled(False) # 测试中关闭桌面弹窗
    notifier.clear_queue()
    notifier._stock_alert_state.clear()
    notifier._last_alert_ts.clear()

    # 1. 首次触发：推送神奇制药 (来源: 每日天梯)，必须成功放行并包含 source 来源
    item_holder = []
    def _mock_enqueue(item):
        item_holder.append(item)
    notifier._enqueue_notification_item = _mock_enqueue

    notifier.notify_special_signal(
        code="600613",
        name="神奇制药",
        reason="👑 空间高度龙 (4板) | 涨幅+10.05%",
        score=92.0,
        source="每日天梯"
    )
    assert len(item_holder) == 1, "首次触发必须成功放行"
    assert item_holder[-1]['source'] == "每日天梯", "必须明确标记报警来源【每日天梯】"
    assert item_holder[-1]['code'] == "600613"

    # 2. 5 秒后推送相同信号：在 10 分钟冷却期内，必须静默拦截
    current_count = len(item_holder)
    notifier.notify_special_signal(
        code="600613",
        name="神奇制药",
        reason="👑 空间高度龙 (4板) | 涨幅+10.08%", # 仅涨幅微小波动
        score=92.0,
        source="每日天梯"
    )
    assert len(item_holder) == current_count, "10分钟内相同同类信号必须静默拦截，不得重复刷屏"

    # 3. 20 秒后出现【新异动信号】(例如出现炸板回封、阳包阴等新形态突变)，必须立即放行！
    notifier.notify_special_signal(
        code="600613",
        name="神奇制药",
        reason="💥 炸板回封强支撑 | 🔥阳包阴反转突破 | 涨幅+10.00%",
        score=94.0,
        source="每日天梯"
    )
    assert len(item_holder) == current_count + 1, "10分钟内出现新形态异动突变必须即时放行"
    assert "阳包阴" in item_holder[-1]['reason']

    # 4. 测试打分大幅提升 (>= 5 分) 即时放行
    notifier.notify_special_signal(
        code="003040",
        name="楚天龙",
        reason="分时突破",
        score=80.0,
        source="赛道热榜"
    )
    assert item_holder[-1]['code'] == "003040"
    assert item_holder[-1]['source'] == "赛道热榜"
    cur_cnt = len(item_holder)

    # 4.1 打分飙升到 88 分 (+8分)，必须立即放行！
    notifier.notify_special_signal(
        code="003040",
        name="楚天龙",
        reason="分时突破",
        score=88.0,
        source="赛道热榜"
    )
    assert len(item_holder) == cur_cnt + 1, "打分显著提升 >= 5分 必须立即放行"

    # 5. 测试 10 分钟 (600秒) 冷却期满后允许再次提醒
    # 人工模拟把楚天龙的上次播报时间调整到 605 秒前
    notifier._stock_alert_state["003040"]['ts'] = time.time() - 605.0
    cur_cnt2 = len(item_holder)
    notifier.notify_special_signal(
        code="003040",
        name="楚天龙",
        reason="分时突破",
        score=88.0,
        source="赛道热榜"
    )
    notifier.clear_queue()


def test_active_buy_early_signal_alert(qapp):
    """测试盘口出现【🔥 主动扫买】时，不等加速涨停即刻捕获并触发先手报警"""
    from ats.tdx_realtime_fetcher import TDXRealtimeFetcher
    fetcher = TDXRealtimeFetcher()

    # 模拟盘口 quotes：*ST正平 (603843) 处于 +3.5% 阶段，但盘口已出现大单主动扫买 (taker_buy_ratio >= 60%)
    quotes = [{
        "code": "603843",
        "name": "*ST正平",
        "price": 7.50,
        "last_close": 7.25,
        "open": 7.28,
        "high": 7.50,
        "low": 7.20,
        "b_vol": 18000,
        "s_vol": 6000,  # 主动买外盘远大于内盘
        "vol": 24000,
        "amount": 18000000.0,
        "bid1": 7.49,
        "ask1": 7.50,
        "bid_vol1": 5000,
        "ask_vol1": 1000,
        "bid_vol2": 4000,
        "ask_vol2": 800,
    }]
    fetcher.get_security_quotes_safe = lambda codes: quotes

    sec_map = {"603843": "赛马概念"}
    parsed = fetcher.fetch_multi_stock_alpha_quotes(["603843"], sector_map=sec_map, multi_period_cache={})

    assert len(parsed) == 1
    item = parsed[0]
    # 1. 验证盘口意图判定为【🔥 主动扫买】
    assert item["order_intent"] == "🔥 主动扫买"
    # 2. 验证买点类型判定为【🔥 主动扫买】或【👑 领涨龙头】（不等涨停即刻给高权重）
    assert "扫买" in item["buy_type"] or "领涨龙头" in item["buy_type"]
    assert item["alpha_score"] >= 72.0, "主动扫买在起步期必须具备高 Alpha 进攻得分"

    # 3. 验证推入 AlertNotifier 时能够顺利放行并带有【赛道热榜】来源
    notifier = AlertNotifier.get_instance()
    pushed_holder = []
    notifier._enqueue_notification_item = lambda it: pushed_holder.append(it)
    notifier.clear_queue()
    notifier._stock_alert_state.clear()

    notifier.notify_special_signal(
        code=item["code"],
        name=item["name"],
        reason=f"{item['sector']} {item['buy_type']} [{item['order_intent']}] | {item['reason']}",
        score=item["alpha_score"],
        source="赛道热榜"
    )

    assert len(pushed_holder) == 1
    assert "主动扫买" in pushed_holder[0]["reason"]
    assert pushed_holder[0]["source"] == "赛道热榜"
    assert pushed_holder[0]["code"] == "603843"
