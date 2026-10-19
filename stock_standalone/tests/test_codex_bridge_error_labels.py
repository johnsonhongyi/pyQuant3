import json
import unittest
from webTools.window_manager.codex_bridge_manager import _friendly_error_code, _format_bridge_log_entry


class BridgeErrorLabelsTests(unittest.TestCase):
    def test_error_codes_have_explanation_and_original_code(self):
        for code, text in (("CLI_ROUTING_DISCOVERY_FAILED", "服务路由"), ("CLI_USAGE_LIMIT", "额度"),
                           ("CLI_NETWORK_ERROR", "连接中断"), ("MODEL_TIMEOUT", "任务时限"),
                           ("CLI_EXIT_CODE_1", "未取得具体原因")):
            label = _friendly_error_code(code)
            self.assertIn(text, label)
            self.assertIn(code, label)

    def test_log_explains_timing_stage_and_recovery_without_valueerror(self):
        _, text, _ = _format_bridge_log_entry(json.dumps({"status":"degraded", "error_code":"MODEL_TIMEOUT",
            "stage":"codex_event", "retry_after_seconds":5, "error_detail":{"type":"ValueError",
            "message":"MODEL_TIMEOUT", "elapsed_ms":156000, "timeout_budget_ms":155000, "received_content":False}}))
        for value in ("等待 Codex 分析事件", "156.0 秒", "155.0 秒", "尚未收到回答内容", "不代表原任务已重试"):
            self.assertIn(value, text)
        self.assertNotIn("value错误", text)

    def test_log_contains_possible_causes_and_action_without_claiming_network_root(self):
        for code in ("CLI_ROUTING_DISCOVERY_FAILED", "CLI_USAGE_LIMIT", "MODEL_TIMEOUT", "CLI_EXIT_CODE_1"):
            _, text, _ = _format_bridge_log_entry(json.dumps({"status":"degraded", "error_code":code}))
            self.assertIn("可能原因：", text)
            self.assertIn("处理建议：", text)
        _, text, _ = _format_bridge_log_entry(json.dumps({"status":"degraded", "error_code":"CLI_EXIT_CODE_1"}))
        self.assertIn("不要仅凭退出码判定断网", text)

    def test_agv_old_location_log_is_not_presented_as_transient_retry(self):
        from webTools.window_manager.antigravity_bridge_manager import _format_agv_logs
        text=_format_agv_logs(json.dumps({"status":"degraded", "error_code":"AGY_RESULT_ERROR", "retry_after_seconds":5,
            "error_detail":{"message":"FAILED_PRECONDITION (code 400): User location is not supported for the API use."}}))
        for expected in ("AGY_LOCATION_UNSUPPORTED", "原始码 AGY_RESULT_ERROR", "可能原因", "处理建议", "此任务不会自动重试"):
            self.assertIn(expected,text)
        self.assertNotIn("可重试",text)
        self.assertNotIn("5 秒后重试",text)

    def test_unknown_error_is_preserved(self):
        self.assertIn("NEW ERROR", _friendly_error_code("NEW_ERROR"))
