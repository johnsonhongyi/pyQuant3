# -*- coding: utf-8 -*-
"""
ATS Startup Profiler
微秒级启动性能检测探针与卡点追踪器。
用于全面监测 ATS 启动过程中各个初始化阶段、UI组件构建、IO读取与网络拉取的耗时，
自动识别超过阈值 (如 >50ms) 的性能卡点并输出结构化看板。
"""

import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("StartupProfiler")


class StartupProfiler:
    _instance: Optional['StartupProfiler'] = None

    def __init__(self):
        self._start_time = time.perf_counter()
        self._checkpoints: List[Dict[str, Any]] = []
        self._last_time = self._start_time
        self._active_sections: Dict[str, float] = {}

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
        if duration_ms >= threshold_warn_ms:
            logger.warning(f"⚠️ [PERF_BOTTLENECK] '{name}' 耗时较高: {duration_ms:.2f}ms (启动累计: {total_elapsed_ms:.2f}ms)")
        else:
            logger.debug(f"⏱️ [PERF] '{name}': {duration_ms:.2f}ms")

    def print_summary(self):
        """打印美观、结构化的启动全链路耗时看板 (安全兼容 Windows GBK/UTF-8 控制台)"""
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
                # 极端环境转 ascii
                print(summary_str.encode('gbk', errors='replace').decode('gbk'))
            except Exception:
                pass
        logger.info(summary_str)
        return summary_str


# 全局便捷函数
def mark_checkpoint(name: str, threshold_warn_ms: float = 50.0):
    StartupProfiler.get_instance().mark(name, threshold_warn_ms)
