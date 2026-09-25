"""Next Day Watch Strategy Configuration Manager.

Acts as the Single Source of Truth (SSOT) for reading, validating, cloning,
and atomically saving next-session candidate strategy configurations.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from next_day_anomaly_watch import (
    _FEATURES,
    _atomic_json,
    _read_json,
    _valid_config,
)
from sys_utils import get_app_root, get_base_path, get_conf_path


class NextDayWatchConfigManager:
    """Manages next-day watch strategy configuration JSON files."""

    CONFIG_FILENAME = "next_day_watch_strategies.json"
    ALLOWED_TEMPLATES = ("channel_stepup",)
    ALLOWED_PROOFS = ("daily_high_break", "verified_vwap_rise")

    @classmethod
    def get_config_path(cls, custom_path: Optional[str] = None) -> str:
        if custom_path:
            return custom_path
        app_root = get_app_root()
        return get_conf_path(cls.CONFIG_FILENAME, app_root)

    @classmethod
    def get_supported_features(cls) -> List[str]:
        """Return the sorted list of supported feature names."""
        return sorted(_FEATURES)

    @classmethod
    def load_config(cls, path: Optional[str] = None) -> Tuple[bool, Dict[str, Any], str]:
        """Load configuration from disk.

        Returns (success, config_dict, error_msg).
        """
        target_path = cls.get_config_path(path)
        data = _read_json(target_path, None)
        valid, err = cls.validate_config(data) if isinstance(data, dict) else (False, "Invalid or missing JSON")
        if valid:
            return True, data, ""

        recovered, recovery_msg = cls._restore_config(target_path)
        if recovered is not None:
            return True, recovered, f"{err}; {recovery_msg}"
        return False, data if isinstance(data, dict) else cls.get_default_config(), f"{err}; {recovery_msg}"

    @classmethod
    def _restore_config(cls, target_path: str) -> Tuple[Optional[Dict[str, Any]], str]:
        """Restore a missing or invalid config while preserving any damaged copy."""
        bundled_path = os.path.join(get_base_path(), "config", cls.CONFIG_FILENAME)
        recovered = _read_json(bundled_path, None)
        valid, _ = cls.validate_config(recovered) if isinstance(recovered, dict) else (False, "missing template")
        if not valid:
            recovered = cls.get_default_config()
            valid, err = cls.validate_config(recovered)
            if not valid:
                return None, f"Built-in defaults are invalid: {err}"

        try:
            if os.path.isfile(target_path) and os.path.getsize(target_path) > 0:
                backup_path = f"{target_path}.invalid.{time.strftime('%Y%m%d_%H%M%S')}.{os.getpid()}"
                import shutil
                shutil.copy2(target_path, backup_path)
            _atomic_json(target_path, recovered)
            return recovered, f"Restored default configuration to {target_path}"
        except Exception as exc:
            return None, f"Configuration restore failed: {exc}"

    @classmethod
    def validate_config(cls, config: Any) -> Tuple[bool, str]:
        """Perform comprehensive validation against schema rules."""
        if not isinstance(config, dict):
            return False, "Configuration must be a JSON object"
        if not isinstance(config.get("enabled"), bool):
            return False, "Top-level 'enabled' must be a boolean"
        valid, err = _valid_config(config)
        if not valid:
            return False, err

        # Extra semantic validation for followup proof rules
        strategies = config.get("strategies", [])
        for strat in strategies:
            followup = strat.get("followup", {})
            if not isinstance(followup, dict):
                return False, f"Strategy {strat.get('strategy_id')} followup must be an object"
            trading_days = followup.get("trading_days")
            if not isinstance(trading_days, int) or trading_days < 1:
                return False, f"Strategy {strat.get('strategy_id')} followup.trading_days must be >= 1"
            proofs = followup.get("proof_any", [])
            if not isinstance(proofs, list) or not proofs:
                return False, f"Strategy {strat.get('strategy_id')} followup.proof_any must not be empty"
            if any(p not in cls.ALLOWED_PROOFS for p in proofs):
                return False, f"Strategy {strat.get('strategy_id')} followup.proof_any contains unsupported proofs"

        return True, ""

    @classmethod
    def save_config(cls, config: Dict[str, Any], path: Optional[str] = None) -> Tuple[bool, str, str]:
        """Atomically persist validated configuration to disk.

        Returns (success, message, config_hash).
        """
        valid, err = cls.validate_config(config)
        if not valid:
            return False, f"Validation failed: {err}", ""

        target_path = cls.get_config_path(path)
        try:
            digest = hashlib.sha256(json.dumps(config, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
            _atomic_json(target_path, config)
            return True, f"Saved successfully to {target_path}", digest
        except Exception as exc:
            return False, f"Atomic write failed: {exc}", ""

    @classmethod
    def clone_strategy_new_version(cls, config: Dict[str, Any], strategy_id: str) -> Tuple[bool, Dict[str, Any], str]:
        """Clone an existing strategy into a new incremented version.

        Preserves historical versions for audit integrity, setting the new one active.
        """
        if not isinstance(config, dict) or "strategies" not in config:
            return False, config, "Invalid configuration structure"

        strategies = config.get("strategies", [])
        target = None
        max_ver = 1
        for s in strategies:
            if s.get("strategy_id") == strategy_id:
                target = s
                try:
                    ver_num = int(s.get("version", 1))
                    if ver_num > max_ver:
                        max_ver = ver_num
                except (ValueError, TypeError):
                    pass

        if target is None:
            return False, config, f"Strategy '{strategy_id}' not found"

        new_strat = copy.deepcopy(target)
        new_strat["version"] = max_ver + 1
        new_strat["enabled"] = True

        # Optionally disable previous version to avoid duplicate running
        for s in strategies:
            if s.get("strategy_id") == strategy_id:
                s["enabled"] = False

        new_config = copy.deepcopy(config)
        new_config["strategies"].append(new_strat)
        return True, new_config, f"Strategy '{strategy_id}' cloned as version {new_strat['version']}"

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """Return the baseline clean default config."""
        return {
            "schema_version": 1,
            "enabled": True,
            "vwap_field": None,
            "strategies": [
                {
                    "strategy_id": "channel_stepup",
                    "version": 1,
                    "enabled": True,
                    "template": "channel_stepup",
                    "required_fields": [
                        "ch_dir", "ch_slope_deg", "ch_pos", "ch_lower", "td_sell",
                        "lastp1d", "lasth1d", "lasth2d", "lasth3d",
                        "lastl1d", "lastl2d", "lastl3d", "lastl4d", "lastl5d",
                        "lastv1d", "lastv2d", "lastv3d"
                    ],
                    "universe": {"include_code_prefixes": [], "exclude_code_prefixes": []},
                    "tiers": [
                        {"id": "A", "rule": "support_stable"},
                        {"id": "B", "rule": "higher_highs_lows"},
                        {"id": "C", "rule": "gentle_volume_growth"}
                    ],
                    "rank_weights": {"A": 1, "B": 2, "C": 3},
                    "thresholds": {
                        "slope_min": 1.5,
                        "ch_pos_min": 5,
                        "ch_pos_max": 60,
                        "support_tolerance": 0.015,
                        "td_sell_max": 5,
                        "low_stability_tolerance": 0.01,
                        "low_stability_count": 2,
                        "volume_ratio_min": 1.1,
                        "volume_ratio_max": 2.5,
                        "daily_volume_floor": 0.9,
                        "volume_growth_days": 2,
                        "volume_spike_max": 3.2
                    },
                    "pre_filter": {
                        "all": [
                            {"field": "ch_dir", "op": "==", "value": 1},
                            {"field": "ch_slope_deg", "op": ">", "value": 1.5},
                            {"field": "ch_pos", "op": "between", "value": [5, 60]}
                        ]
                    },
                    "capacity": {"A": 100, "B": 60, "C": 40},
                    "followup": {
                        "trading_days": 3,
                        "proof_any": ["daily_high_break", "verified_vwap_rise"]
                    }
                }
            ]
        }
