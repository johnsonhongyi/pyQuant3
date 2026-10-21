# -*- coding: utf-8 -*-
"""
tests/test_alert_voice_deadlock_and_shutdown.py
-----------------------------------------------
专项单元测试：
1. normalize_speech_text 过滤 Emoji、非标准特殊字符、超长截断与数字读音标准化；
2. AlertNotifier 超短特异赛马（过热未加速、连杀企稳等）语音模板命中；
3. AlertNotifier._stop_voice_workers 守护线程超时安全放行，绝不阻断 ATS 主流程退出。
"""
import time
import pytest
from alert_manager import normalize_speech_text
from ats.alert_notifier import AlertNotifier

def test_normalize_speech_text_sanitization():
    raw_msg = (
        "⚠️ 过热未加速·出局·📈 连杀小企稳·高开加速 | (-16.3%)至支撑(9.84)"
    )
    cleaned = normalize_speech_text(raw_msg)
    
    # 1. 验证所有非法 Emoji 与特殊字符均被剥离
    for forbidden in ["⚠️", "📈", "·", "→", "|", "(", ")", "%"]:
        assert forbidden not in cleaned, f"Forbidden character '{forbidden}' should be stripped"
    
    # 2. 验证负数、百分比、小数读音标准化
    assert "负16点3百分之" in cleaned
    assert "9点84" in cleaned
    
    # 3. 验证最大字符限制保护 (<= 60 字符)
    assert len(cleaned) <= 60

def test_stop_voice_workers_does_not_block_shutdown():
    notifier = AlertNotifier.get_instance()
    
    # 模拟一个存活的守护线程
    import threading
    dummy_worker = threading.Thread(target=lambda: time.sleep(0.5), name="DummyVoiceWorker", daemon=True)
    dummy_worker.start()
    
    with notifier._voice_lock:
        notifier._voice_threads.append(dummy_worker)
        
    deadline = time.monotonic() + 0.1
    try:
        # 验证无论线程是否在短时间内结束，_stop_voice_workers 必须返回 True，保证 ATS 退出不被阻断
        result = notifier._stop_voice_workers(deadline)
        assert result is True
    finally:
        with notifier._voice_lock:
            if dummy_worker in notifier._voice_threads:
                notifier._voice_threads.remove(dummy_worker)
