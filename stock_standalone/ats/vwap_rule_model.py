# -*- coding: utf-8 -*-
"""
ats/vwap_rule_model.py
----------------------
分时交易策略规则配置模型与热加载管理器。
支持 JSON 配置解析、参数校验、默认规则兜底以及盘中毫秒级热加载（Hot-Reload）。
"""

import json
import os
import threading
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, List

logger = logging.getLogger("VWAPRuleModel")

DEFAULT_CONFIG_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "config", "vwap_trading_rules.json")
)


@dataclass
class AggressiveBuyRule:
    id: str
    name: str
    enabled: bool
    priority: int
    conditions: Dict[str, Any]
    action_type: str
    size_pct: float


@dataclass
class ConservativeOversightConfig:
    enabled: bool
    consensus_required: bool
    veto_on_hesitation: bool
    min_structure_clarity: float
    max_hesitation_star_ratio: float
    min_consolidation_minutes: int
    max_consolidation_range_pct: float
    min_volume_ratio: float
    min_multi_period_score: float
    max_dff_outflow: float


@dataclass
class ExitLayerConfig:
    id: str
    name: str
    enabled: bool
    priority: int
    params: Dict[str, Any]


class VWAPRuleModel:
    """
    分时均价策略规则模型（线程安全单例或实例）
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._lock = threading.RLock()
        self._raw_config: Dict[str, Any] = {}
        self._last_mtime: float = 0.0
        self._change_callbacks: List[Callable[[Dict[str, Any]], None]] = []
        
        self.aggressive_rules: List[AggressiveBuyRule] = []
        self.conservative_config: Optional[ConservativeOversightConfig] = None
        self.exit_layers: Dict[str, ExitLayerConfig] = {}
        self.guardian_rules: Dict[str, Any] = {}
        
        self.reload()

    def register_change_callback(self, cb: Callable[[Dict[str, Any]], None]) -> None:
        """注册配置变更回调通知"""
        with self._lock:
            if cb not in self._change_callbacks:
                self._change_callbacks.append(cb)

    def reload(self) -> bool:
        """重新从磁盘加载规则配置"""
        with self._lock:
            if not os.path.exists(self.config_path):
                logger.warning(f"规则配置文件不存在: {self.config_path}，使用硬编码兜底配置")
                self._apply_fallback_config()
                return False

            try:
                mtime = os.path.getmtime(self.config_path)
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                self._raw_config = data
                self._last_mtime = mtime
                self._parse_config(data)
                logger.info(f"成功加载策略规则配置: {self.config_path} (版本: {data.get('version')})")
                
                # 触发监听回调
                for cb in self._change_callbacks:
                    try:
                        cb(self._raw_config)
                    except Exception as e:
                        logger.error(f"规则热更新回调执行异常: {e}")
                        
                return True
            except Exception as exc:
                logger.error(f"解析规则配置失败: {exc}，保留原配置或使用兜底")
                if not self._raw_config:
                    self._apply_fallback_config()
                return False

    def check_and_reload_if_modified(self) -> bool:
        """检测文件是否有修改，有修改则自动热重载"""
        with self._lock:
            if not os.path.exists(self.config_path):
                return False
            try:
                mtime = os.path.getmtime(self.config_path)
                if mtime > self._last_mtime:
                    return self.reload()
            except Exception:
                pass
            return False

    def _parse_config(self, data: Dict[str, Any]) -> None:
        """解析 JSON 为结构化规则对象"""
        groups = data.get("strategy_groups", {})
        
        # 1. 激进组规则
        agg = groups.get("aggressive", {})
        self.aggressive_rules = []
        for r in agg.get("buy_rules", []):
            action = r.get("action", {})
            self.aggressive_rules.append(
                AggressiveBuyRule(
                    id=r.get("id", ""),
                    name=r.get("name", ""),
                    enabled=bool(r.get("enabled", True)),
                    priority=int(r.get("priority", 50)),
                    conditions=r.get("conditions", {}),
                    action_type=action.get("type", "BUY_SCOUT"),
                    size_pct=float(action.get("size_pct", 0.1)),
                )
            )

        # 2. 保守组（辅助监管审查员）
        con = groups.get("conservative", {})
        params = con.get("parameters", {})
        self.conservative_config = ConservativeOversightConfig(
            enabled=bool(con.get("enabled", True)),
            consensus_required=bool(con.get("consensus_required", True)),
            veto_on_hesitation=bool(con.get("veto_on_hesitation", True)),
            min_structure_clarity=float(params.get("min_structure_clarity", 70.0)),
            max_hesitation_star_ratio=float(params.get("max_hesitation_star_ratio", 0.40)),
            min_consolidation_minutes=int(params.get("min_consolidation_minutes", 15)),
            max_consolidation_range_pct=float(params.get("max_consolidation_range_pct", 1.0)),
            min_volume_ratio=float(params.get("min_volume_ratio", 1.2)),
            min_multi_period_score=float(params.get("min_multi_period_score", 75.0)),
            max_dff_outflow=float(params.get("max_dff_outflow", -0.2)),
        )

        # 3. 8层递进离场守护
        exit_cfg = data.get("proactive_exit_rules", {})
        self.exit_layers = {}
        layers = exit_cfg.get("layers", {})
        for layer_key, ldata in layers.items():
            lid = ldata.get("id", layer_key)
            self.exit_layers[lid] = ExitLayerConfig(
                id=lid,
                name=ldata.get("name", lid),
                enabled=bool(ldata.get("enabled", True)),
                priority=int(ldata.get("priority", 50)),
                params={k: v for k, v in ldata.items() if k not in ["id", "name", "enabled", "priority"]},
            )

        # 4. 宏观守护规则
        self.guardian_rules = data.get("market_guardian_rules", {})

    def _apply_fallback_config(self) -> None:
        """兜底配置，避免文件缺失导致崩溃"""
        self.aggressive_rules = [
            AggressiveBuyRule(
                id="buy_vwap_base_breakout",
                name="VWAP筑底突破(兜底)",
                enabled=True,
                priority=85,
                conditions={"price_crossing_vwap": True, "min_volume_ratio": 1.1},
                action_type="BUY_SCOUT",
                size_pct=0.10,
            )
        ]
        self.conservative_config = ConservativeOversightConfig(
            enabled=True,
            consensus_required=True,
            veto_on_hesitation=True,
            min_structure_clarity=70.0,
            max_hesitation_star_ratio=0.40,
            min_consolidation_minutes=15,
            max_consolidation_range_pct=1.0,
            min_volume_ratio=1.2,
            min_multi_period_score=75.0,
            max_dff_outflow=-0.2,
        )
        self.exit_layers = {
            "exit_failed_rally": ExitLayerConfig("exit_failed_rally", "反弹前高不过", True, 90, {}),
            "exit_vwap_breakdown": ExitLayerConfig("exit_vwap_breakdown", "VWAP破位兜底", True, 60, {}),
        }
        self.guardian_rules = {"enabled": True}

    def get_exit_layer_param(self, layer_id: str, param_name: str, default: Any = None) -> Any:
        """安全读取某层出局参数"""
        with self._lock:
            layer = self.exit_layers.get(layer_id)
            if layer and layer.enabled:
                return layer.params.get(param_name, default)
            return default
