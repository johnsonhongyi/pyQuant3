# -*- coding: utf-8 -*-
"""
ATS Startup Profiler
微秒级启动性能检测探针与卡点追踪器。
用于全面监测 ATS 启动过程中各个初始化阶段、UI组件构建、IO读取与网络拉取的耗时，
自动识别超过阈值 (如 >50ms) 的性能卡点并输出结构化看板。
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("StartupProfiler")
PROFILER_CONFIG_KEY = "ats_startup_profiler_enabled"


class StartupProfiler:
    _instance: Optional['StartupProfiler'] = None

    def __init__(self):
        self._start_time = time.perf_counter()
        self._checkpoints: List[Dict[str, Any]] = []
        self._last_time = self._start_time
        self._active_sections: Dict[str, float] = {}
        self.is_enabled = self._load_enabled_state()

    def _load_enabled_state(self) -> bool:
        """从持久化配置中读取性能分析看板开关 (默认关闭，杜绝刷屏)"""
        try:
            from sys_utils import get_app_root, get_conf_path
            cfg_path = get_conf_path("window_config.json", get_app_root())
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return bool(data.get(PROFILER_CONFIG_KEY, False))
        except Exception:
            pass
        return False

    def set_enabled(self, enabled: bool):
        """设置性能分析开关并自动原子持久化落盘"""
        self.is_enabled = bool(enabled)
        try:
            from sys_utils import get_app_root, get_conf_path
            cfg_path = get_conf_path("window_config.json", get_app_root())
            data = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data[PROFILER_CONFIG_KEY] = self.is_enabled
            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    @classmethod
    def get_instance(cls) -> 'StartupProfiler':
        if cls._instance is None:
            cls._instance = StartupProfiler()
        return cls._instance

    @classmethod
    def reset(cls) -> 'StartupProfiler':
        cls._instance = StartupProfiler()
        return cls._instance

    def mark(self, name: str, threshold_warn_ms: float = 50.0):
        """记录一个瞬时里程碑耗时"""
        now = time.perf_counter()
        duration_ms = (now - self._last_time) * 1000.0
        total_elapsed_ms = (now - self._start_time) * 1000.0
        self._checkpoints.append({
            "name": name,
            "duration_ms": duration_ms,
            "total_elapsed_ms": total_elapsed_ms,
            "warn": duration_ms >= threshold_warn_ms
        })
        self._last_time = now
        if self.is_enabled:
            if duration_ms >= threshold_warn_ms:
                logger.warning(f"⚠️ [PERF_BOTTLENECK] '{name}' 耗时较高: {duration_ms:.2f}ms (启动累计: {total_elapsed_ms:.2f}ms)")
            else:
                logger.debug(f"⏱️ [PERF] '{name}': {duration_ms:.2f}ms")

    def print_summary(self, force: bool = False):
        """打印美观、结构化的启动全链路耗时看板 (默认遵循持久化开关，仅在开启或 force 时输出)"""
        if not self.is_enabled and not force:
            return ""

        total_time_ms = (time.perf_counter() - self._start_time) * 1000.0
        header_title = f"[ATS Startup Profiler] 启动全链路性能耗时看板 (总耗时: {total_time_ms:.2f} ms)"
        lines = [
            "\n" + "=" * 80,
            header_title,
            "=" * 80,
            f"{'阶段 / 组件名称':<45} | {'耗时 (ms)':<12} | {'占比':<8} | {'状态'}",
            "-" * 80
        ]
        
        for cp in self._checkpoints:
            name = cp["name"]
            dur = cp["duration_ms"]
            pct = (dur / total_time_ms * 100.0) if total_time_ms > 0 else 0.0
            status = "[WARN] 慢" if cp["warn"] else "[OK] 极速"
            lines.append(f"{name:<45} | {dur:>9.2f} ms | {pct:>6.1f}% | {status}")
            
        lines.append("=" * 80 + "\n")
        summary_str = "\n".join(lines)
        try:
            import sys
            if hasattr(sys.stdout, 'reconfigure'):
                try:
                    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                except Exception:
                    pass
            print(summary_str)
        except Exception:
            try:
                print(summary_str.encode('gbk', errors='replace').decode('gbk'))
            except Exception:
                pass
        logger.info(summary_str)
        return summary_str


# 全局便捷函数
def mark_checkpoint(name: str, threshold_warn_ms: float = 50.0):
    StartupProfiler.get_instance().mark(name, threshold_warn_ms)
