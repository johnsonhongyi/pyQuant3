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

import shutil

try:
    from sys_utils import get_app_root, get_base_path
except ImportError:
    def get_app_root() -> str:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    def get_base_path() -> str:
        return get_app_root()

logger = logging.getLogger("VWAPRuleModel")


def _get_rule_version_and_content(file_or_dict) -> tuple:
    """安全解析规则配置的版本号与内容文本，用于版本比对"""
    try:
        if isinstance(file_or_dict, dict):
            ver = float(file_or_dict.get("version", "1.0"))
            return ver, json.dumps(file_or_dict)
        if os.path.exists(file_or_dict):
            with open(file_or_dict, "r", encoding="utf-8") as f:
                txt = f.read()
            d = json.loads(txt)
            ver = float(d.get("version", "1.0"))
            return ver, txt
    except Exception:
        pass
    return 1.0, ""


def resolve_and_ensure_config_path() -> str:
    """
    智能定位并确保 vwap_trading_rules.json 配置文件存在，并支持包内/新版配置自动热升级释放：
    1. 严格使用 sys_utils.get_app_root() 获取外部物理应用程序根目录 (打包 EXE 所在目录或源码根目录)；
    2. 目标文件位于 target_path = os.path.join(get_app_root(), "config", "vwap_trading_rules.json")；
    3. 智能版本与特征比对：
       - 若 target_path 不存在，自动从包内只读资源或源码目录复制释放；
       - 若 target_path 已存在，但包内只读资源/源码的规则版本更高 (如 v2.2 > v2.1) 或目标文件缺失新规则：
         自动将外部旧配置安全备份为 vwap_trading_rules.json.bak_v{old}，并将最新版配置自动释放覆盖！
    4. 彻底解决 PyInstaller / Nuitka 打包发布后外部残留旧配置导致最新策略无法生效的问题。
    """
    app_root = get_app_root()
    target_config = os.path.abspath(os.path.join(app_root, "config", "vwap_trading_rules.json"))
    os.makedirs(os.path.dirname(target_config), exist_ok=True)

    # 尝试源目录候选 (包内只读资源 或 源码相对路径)
    candidate_sources = [
        os.path.join(get_base_path(), "config", "vwap_trading_rules.json"),
        os.path.join(os.path.dirname(__file__), "..", "config", "vwap_trading_rules.json"),
        os.path.join(os.path.dirname(__file__), "config", "vwap_trading_rules.json"),
    ]

    best_src = None
    best_src_ver = 1.0
    best_src_content = ""
    for src in candidate_sources:
        src_abs = os.path.abspath(src)
        if os.path.exists(src_abs) and os.path.getsize(src_abs) > 20:
            ver, content = _get_rule_version_and_content(src_abs)
            if ver >= best_src_ver:
                best_src = src_abs
                best_src_ver = ver
                best_src_content = content

    target_exists = os.path.exists(target_config) and os.path.getsize(target_config) > 20
    target_ver, target_content = _get_rule_version_and_content(target_config) if target_exists else (0.0, "")

    # 1. 命中有效源文件
    if best_src:
        if not target_exists:
            try:
                shutil.copy2(best_src, target_config)
                logger.info(f"已首次从包内资源释放策略配置: {best_src} -> {target_config} (v{best_src_ver})")
                return target_config
            except Exception as e:
                logger.warning(f"复制策略配置文件异常: {e}")
        elif os.path.normpath(best_src).lower() != os.path.normpath(target_config).lower():
            # 外部目标文件已存在，但不是同一文件：检查是否需要升级覆盖
            # 升级触发条件：源版本更高，或目标文件缺失 buy_vwap_displacement_reversal 规则
            needs_upgrade = (best_src_ver > target_ver) or (
                "buy_vwap_displacement_reversal" in best_src_content and "buy_vwap_displacement_reversal" not in target_content
            )
            if needs_upgrade:
                try:
                    import time
                    bak_path = target_config + f".bak_v{target_ver}_{int(time.time())}"
                    shutil.copy2(target_config, bak_path)
                    shutil.copy2(best_src, target_config)
                    logger.info(f"🚀 [自动热升级] 检测到打包环境策略配置版本更新 (v{best_src_ver} > v{target_ver})，已备份旧配置至 {os.path.basename(bak_path)} 并自动释放最新配置到: {target_config}")
                except Exception as err:
                    logger.warning(f"升级覆盖最新策略配置文件异常: {err}")
            return target_config
        else:
            return target_config

    # 内置标准规则兜底释放
    builtin_rules = {
        "version": "2.2",
        "hot_reload": True,
        "description": "ATS/SBC 全自动分时多周期交易系统策略规则（防守优先 + 双组投票共用仓位 + 底抬高反转）",
        "strategy_groups": {
            "aggressive": {
                "name": "激进组",
                "enabled": True,
                "role": "momentum_attacker",
                "buy_rules": [
                    {
                        "id": "buy_vwap_displacement_reversal",
                        "name": "底抬高VWAP位移反转突破",
                        "enabled": True,
                        "priority": 95,
                        "conditions": {
                            "reversal_structure": True,
                            "higher_low_confirmed": True,
                            "vwap_displacement_up": True
                        },
                        "action": {
                            "type": "BUY_SCOUT",
                            "size_pct": 0.25
                        }
                    },
                    {
                        "id": "buy_vwap_base_breakout",
                        "name": "VWAP筑底突破",
                        "enabled": True,
                        "priority": 85,
                        "conditions": {
                            "price_crossing_vwap": True,
                            "min_consolidation_minutes": 10,
                            "max_consolidation_range_pct": 1.2,
                            "min_volume_ratio": 1.1,
                            "vwap_directions": ["UP", "FLAT"],
                            "min_multi_period_score": 65
                        },
                        "action": {
                            "type": "BUY_SCOUT",
                            "size_pct": 0.15
                        }
                    }
                ]
            },
            "conservative": {
                "name": "保守组",
                "enabled": True,
                "role": "risk_sentinel",
                "consensus_required": True,
                "veto_on_hesitation": True,
                "parameters": {
                    "min_structure_clarity": 70.0,
                    "max_hesitation_star_ratio": 0.40,
                    "min_consolidation_minutes": 15,
                    "max_consolidation_range_pct": 1.0,
                    "min_volume_ratio": 1.2,
                    "min_multi_period_score": 75.0,
                    "max_dff_outflow": -0.2
                }
            }
        },
        "proactive_exit_rules": {
            "enabled": True,
            "layers": {
                "layer1_time_decay": {"id": "layer1_time_decay", "name": "时间衰减保护", "enabled": True, "priority": 100},
                "layer2_no_volume": {"id": "layer2_no_volume", "name": "无量不涨离场", "enabled": True, "priority": 95},
                "layer3_failed_rally": {"id": "layer3_failed_rally", "name": "反弹前高不过", "enabled": True, "priority": 90},
                "layer4_distribution": {"id": "layer4_distribution", "name": "冲高派发出局", "enabled": True, "priority": 85},
                "layer5_oscillation_no_new_high": {"id": "layer5_oscillation_no_new_high", "name": "震荡不创新高", "enabled": True, "priority": 80},
                "layer6_volume_price_divergence": {"id": "layer6_volume_price_divergence", "name": "量价背离出局", "enabled": True, "priority": 75},
                "layer7_multi_timeframe_rollover": {"id": "layer7_multi_timeframe_rollover", "name": "大级别MA5d破位", "enabled": True, "priority": 70},
                "layer8_vwap_break_final": {"id": "layer8_vwap_break_final", "name": "VWAP均价线破位终极兜底", "enabled": True, "priority": 60}
            }
        },
        "market_guardian_rules": {"enabled": True}
    }
    try:
        if target_exists:
            import time
            bak_path = target_config + f".bak_v{target_ver}_{int(time.time())}"
            try:
                shutil.copy2(target_config, bak_path)
            except Exception:
                pass
        tmp_path = target_config + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(builtin_rules, f, ensure_ascii=False, indent=2)
        if os.path.exists(target_config):
            os.remove(target_config)
        os.replace(tmp_path, target_config)
        logger.info(f"已自动生成并释放初始策略配置文件: {target_config} (v{builtin_rules.get('version')})")
    except Exception as e:
        logger.error(f"释放初始策略配置异常: {e}")

    return target_config


DEFAULT_CONFIG_PATH = resolve_and_ensure_config_path()


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
                recovered = resolve_and_ensure_config_path()
                if os.path.exists(recovered):
                    self.config_path = recovered
                else:
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
                logger.debug(f"成功加载策略规则配置: {self.config_path} (版本: {data.get('version')})")
                
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
                    result = self.reload()
                    if result:
                        logger.info(f"🔄 [热重载] 策略规则配置已更新: {self.config_path}")
                    return result
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
