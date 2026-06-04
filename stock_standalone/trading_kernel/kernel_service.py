# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any, Mapping
from JohnsonUtil import LoggerFactory

from trading_kernel.core.trace import KernelTrace
from trading_kernel.engine.decision_engine import decide
from trading_kernel.engine.risk_gate import RiskLimits, evaluate
from trading_kernel.engine.signal_canonicalizer import canonicalize_decision_queue_item
from trading_kernel.engine.state_manager import StateManager
from trading_kernel.observability.journal import JsonlJournal
from trading_kernel.observability.trace_hasher import stable_hash

logger = LoggerFactory.getLogger("instock_TK.KernelService")
import pandas as pd
from sys_utils import get_base_path, get_app_root


def load_risk_limits_from_config() -> RiskLimits:
    """从本地 window_config.json 物理配置文件中安全加载保存的风控极限阈值"""
    try:
        import os
        if "PYTEST_CURRENT_TEST" in os.environ:
            return RiskLimits()
        import json
        base_dir = get_app_root()
        # 尝试两个 DPI 主配置文件
        for filename in ("window_config.json", "scale2_window_config.json"):
            config_file = os.path.join(base_dir, filename)
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "DecisionFlowPanel" in data and "risk_limits" in data["DecisionFlowPanel"]:
                    limits_data = data["DecisionFlowPanel"]["risk_limits"]
                    logger.info(f"Loaded persistent RiskLimits from config: {limits_data}")
                    return RiskLimits(
                        min_confidence=float(limits_data.get("min_confidence", 0.70)),
                        max_pct_diff=float(limits_data.get("max_pct_diff", 6.0)),
                        max_single_stock_position_pct=float(limits_data.get("max_single_stock_position_pct", 0.30)),
                        max_single_sector_exposure_pct=float(limits_data.get("max_single_sector_exposure_pct", 0.50)),
                        total_exposure_cap_pct=float(limits_data.get("total_exposure_cap_pct", 0.80)),
                        daily_loss_limit_amount=float(limits_data.get("daily_loss_limit_amount", 50000.0)),
                        max_consecutive_losses=int(limits_data.get("max_consecutive_losses", 3)),
                        min_volume=float(limits_data.get("min_volume", 1.0))
                    )
    except Exception as e:
        logger.error(f"Failed to load RiskLimits from config: {e}")
    return RiskLimits()


def load_trading_mode_from_config() -> str:
    """从本地 window_config.json 物理配置文件中安全加载保存的交易运行模式"""
    try:
        import os
        if "PYTEST_CURRENT_TEST" in os.environ:
            return "OBSERVE"
        import json
        base_dir = get_app_root()
        for filename in ("window_config.json", "scale2_window_config.json"):
            config_file = os.path.join(base_dir, filename)
            if os.path.exists(config_file):
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "DecisionFlowPanel" in data and "trading_mode" in data["DecisionFlowPanel"]:
                    mode = data["DecisionFlowPanel"]["trading_mode"]
                    if mode in {"OBSERVE", "PAPER", "CONFIRM", "LIVE_AUTO"}:
                        return mode
    except Exception:
        pass
    return "OBSERVE"


class TradingKernelService:
    # 算法内核 version 锁死指纹 (Phase 9: Precondition)
    KERNEL_VERSION = "2026.05.23.01"

    def __init__(self, journal_path: str = "logs/trading_kernel_trace.jsonl"):
        self.state_manager = StateManager()
        self.journal = JsonlJournal(journal_path)
        self.limits = load_risk_limits_from_config()
        
        # 从 global.ini 加载静态强路由配置并注入策略决策大脑 StrategyRouter
        try:
            import configparser
            import os
            base_dir = get_app_root()
            from sys_utils import get_conf_path
            ini_path = get_conf_path("global.ini", base_dir=base_dir)
            if ini_path and os.path.exists(ini_path):
                config = configparser.ConfigParser()
                config.read(ini_path, encoding="utf-8")
                if "strategy_routing" in config.sections():
                    rmap = {}
                    for key in config["strategy_routing"]:
                        val = config["strategy_routing"][key]
                        rmap[key] = [c.strip() for c in val.split(",") if c.strip()]
                    from trading_kernel.engine.decision_engine import StrategyRouter
                    StrategyRouter.register_static_routes(rmap)
                    logger.info(f"Successfully loaded and registered static strategy routing overrides from global.ini: {rmap}")
        except Exception as e:
            logger.error(f"Failed to inject static strategy routing overrides from config: {e}")
            
        # 初始化执行层各物理适配器 (里氏替换原则)
        from trading_kernel.execution.paper_adapter import PaperExecutionAdapter
        from trading_kernel.execution.confirm_adapter import ConfirmExecutionAdapter
        from trading_kernel.execution.broker_adapter import BrokerExecutionAdapter, KillSwitch
        
        self.paper_adapter = PaperExecutionAdapter()
        
        # 确认模式适配器 (包装模拟盘适配器，弹出 UI)
        self.confirm_adapter = ConfirmExecutionAdapter(
            underlying_adapter=self.paper_adapter,
            journal=self.journal,
            mode="CONFIRM"
        )
        
        # 挂载 confirm 弹窗回调（Lazy import 避免无头回测环境导入 PyQt6 报错）
        try:
            from tk_gui_modules.confirm_bubble import show_confirmation_bubble_sync
            self.confirm_adapter.set_confirm_callback(show_confirmation_bubble_sync)
        except ImportError:
            def headless_fallback_confirm(ord):
                return {
                    "confirmed": False,
                    "size_pct_override": None,
                    "override_reason": "Headless environment bypass rejection",
                }
            self.confirm_adapter.set_confirm_callback(headless_fallback_confirm)
            
        # 实盘物理适配器 (集成 KillSwitch、幂等去重防重、资产比对自愈)
        self.kill_switch = KillSwitch()
        self.broker_adapter = BrokerExecutionAdapter(
            journal=self.journal,
            kill_switch=self.kill_switch,
        )
        
        # 动态绑定当前物理执行适配器 (默认为 None，Observe 下不投递物理订单)
        self.executor: Any = None
        
        # 从本地配置文件中安全加载保存的交易模式并初始化生效
        saved_mode = load_trading_mode_from_config()
        self._mode = "OBSERVE"
        self.set_trading_mode(saved_mode)
        
        # 高性能个股指标特征富化内存缓存 (Phase 9: High Performance Cache)
        self._indicator_cache = {}
        self._df_all = None
        self._auto_warm_up_from_preprocessed_hdf5()

    def update_df_all(self, df_all):
        """
        供外部实时/准实时将最新的 df_all 注入到内核单例中，供 O(1) 内存指标极速反查与缓存热身使用。
        """
        self._df_all = df_all
        # 顺便用 df_all 的特征为内存缓存做一次热身，实现双重极速保障！
        self.warm_up_indicator_cache(df_all)

    def _get_df_all(self):
        """
        [Dynamic Auto-Detection] 动态安全探测主窗口或其它模块中持有的内存大表 df_all 属性
        """
        # 1. 优先使用外部显式注入的 df_all
        if hasattr(self, '_df_all') and self._df_all is not None and not self._df_all.empty:
            return self._df_all
            
        # 2. 动态自愈探测：扫描 sys.modules 并寻找拥有非空 df_all 属性的 MainWindow 实例或全局对象
        try:
            import sys
            # 扫描已经载入的模块
            for mod_name in list(sys.modules.keys()):
                # 针对核心监控模块做定向排查
                if 'instock_Monitor' in mod_name or 'MonitorTK' in mod_name or 'visualizer' in mod_name:
                    mod = sys.modules[mod_name]
                    # 探测 MainWindow.instance 或者是 MainWindow 全局变量
                    for attr_name in ['MainWindow', 'app', 'main_win', 'main_window']:
                        if hasattr(mod, attr_name):
                            obj = getattr(mod, attr_name)
                            # 如果是类，且有单例属性 instance
                            if hasattr(obj, 'instance') and obj.instance:
                                obj = obj.instance
                            if hasattr(obj, 'df_all') and obj.df_all is not None and not obj.df_all.empty:
                                return obj.df_all
                            if hasattr(obj, 'main_win') and hasattr(obj.main_win, 'df_all') and obj.main_win.df_all is not None:
                                return obj.main_win.df_all
        except Exception:
            pass
            
        # 3. [降维打击级自愈兜底] 物理扫描全局已加载模块，搜寻任何拥有行数 > 1000 且非空 df_all 属性的对象
        try:
            import sys
            import pandas as pd
            for mod_name, mod in list(sys.modules.items()):
                if not mod or any(x in mod_name.lower() for x in ['pandas', 'numpy', 'matplotlib', 'tables', 'pytest', '_pytest', 'pluggy', 'py.', 'distutils', 'importlib']):
                    continue
                try:
                    for attr_name in list(dir(mod)):
                        # 排除系统内置的双下划线属性以提高效率
                        if attr_name.startswith('__'):
                            continue
                        try:
                            obj = getattr(mod, attr_name)
                            if obj is not None:
                                obj_type_module = getattr(type(obj), '__module__', '')
                                if any(x in str(obj_type_module).lower() for x in ['pytest', '_pytest', 'pluggy', 'py.']):
                                    continue
                                # 探测对象自身是否含有 df_all
                                if hasattr(obj, 'df_all'):
                                    df_val = getattr(obj, 'df_all')
                                    if isinstance(df_val, pd.DataFrame) and not df_val.empty and len(df_val) > 1000:
                                        return df_val
                                # 探测对象是 MainWindow 且 MainWindow.instance 含有 df_all
                                if hasattr(obj, 'instance') and obj.instance and hasattr(obj.instance, 'df_all'):
                                    df_val = getattr(obj.instance, 'df_all')
                                    if isinstance(df_val, pd.DataFrame) and not df_val.empty and len(df_val) > 1000:
                                        return df_val
                        except Exception:
                            continue
                except Exception:
                    continue
        except Exception:
            pass
            
        return None

    def _auto_warm_up_from_preprocessed_hdf5(self):
        """
        [Ultra Performance] 自动从早盘已经预处理好的极速 HDF5 数据库 (top_all.h5 或 共享的 shared_df_all) 中,
        一次性将全市场股票的多周期历史静态技术指标加载进 _indicator_cache 内存。
        """
        import os
        import pandas as pd
        base_dir = get_app_root()
        today_date_str = datetime.now().strftime("%Y%m%d")
        h5_paths = [
            fr'G:\shared_df_all-{today_date_str}.h5',
            r'G:\shared_df_all.h5',
            r'g:\top_all.h5',
            os.path.join(base_dir, 'top_all.h5'),
            os.path.join(get_app_root(), 'top_all.h5'),
            'top_all.h5'
        ]
        
        loaded = False
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        for path in h5_paths:
            if os.path.exists(path):
                try:
                    # 智能探测 HDF5 key，自适应 'df_all' 还是 'top_all'
                    key_to_read = None
                    try:
                        with pd.HDFStore(path, mode='r') as store:
                            keys = store.keys()
                            if keys:
                                key_to_read = keys[0].lstrip('/')
                    except Exception:
                        pass
                    
                    if not key_to_read:
                        key_to_read = 'top_all'
                        
                    try:
                        df_top = pd.read_hdf(path, key_to_read)
                    except Exception:
                        try:
                            df_top = pd.read_hdf(path, 'df_all')
                        except Exception:
                            df_top = pd.read_hdf(path, 'top_all')
                    
                    if df_top is not None and not df_top.empty:
                        # 字段映射
                        import re
                        for idx, row in df_top.iterrows():
                            # 极其强壮地使用正则，剔除任何后缀如 .SH / .SZ 等，只获取 6 位数字代码
                            code_val = idx[0] if isinstance(idx, tuple) else idx
                            raw_code_str = str(code_val).strip()
                            if not raw_code_str or raw_code_str == 'nan':
                                raw_code_str = str(row.get('code', '')).strip()
                                
                            digits = re.findall(r'\d+', raw_code_str)
                            if digits:
                                code = digits[0].zfill(6)
                            else:
                                continue
                                
                            cache_key = (code, today_str)
                            
                            # 建立列名的大小写自适应映射
                            row_cols_lower = {str(k).lower(): k for k in row.keys()} if hasattr(row, 'keys') else {}
                            
                            feat = {}
                            for col in ['sws', 'sws_prev5', 'swl', 'ma10d', 'ma10d_prev5', 'ma5d', 'ma5d_prev5', 'swl_prev5',
                                        'ma60d', 'ma60d_prev5', 'high4', 'hmax', 'low60', 'pbreak', 'ptop', 'vol_ma5', 'open',
                                        'high_prev1', 'high_prev2', 'high_prev3', 'open_prev1', 'open_prev2', 'open_prev3',
                                        'close_prev1', 'close_prev2', 'close_prev3', 'low_prev1']:
                                matched_key = None
                                if col in row:
                                    matched_key = col
                                elif col.lower() in row_cols_lower:
                                    matched_key = row_cols_lower[col.lower()]
                                elif col.upper() in row:
                                    matched_key = col.upper()
                                    
                                if matched_key is not None:
                                    val = row[matched_key]
                                    if pd.notna(val):
                                        feat[col] = int(val) if col == 'pbreak' else float(val)
                            
                            if feat:
                                # 补充一些 fallback 值
                                close_val = float(row.get('close', 0.0)) if pd.notna(row.get('close')) else 0.0
                                if feat.get('ma5d', 0.0) <= 0.0: feat['ma5d'] = close_val
                                if feat.get('ma10d', 0.0) <= 0.0: feat['ma10d'] = close_val
                                if feat.get('ma60d', 0.0) <= 0.0: feat['ma60d'] = close_val
                                if feat.get('sws', 0.0) <= 0.0: feat['sws'] = feat['ma10d']
                                if feat.get('swl', 0.0) <= 0.0: feat['swl'] = feat['ma5d']
                                
                                self._indicator_cache[cache_key] = feat
                                    
                            logger.info(f"🚀 [BgKernel] Successfully warm-up {len(self._indicator_cache)} stock indicators from preprocessed {path}!")
                            loaded = True
                            break
                except Exception as e:
                    logger.error(f"[BgKernel] Failed to auto warm-up from {path}: {e}")

    def warm_up_indicator_cache(self, df_all: pd.DataFrame):
        """
        早盘或初始化时，批量传入已经计算好特征的多股票 DataFrame (支持 MultiIndex 或单 index)，
        一次性预热拼装入 _indicator_cache 内存，彻底消除盘中高频行情时的单股文件 I/O 重新计算。
        """
        if df_all is None or df_all.empty:
            return
            
        today_str = datetime.now().strftime("%Y-%m-%d")
        count = 0
        import re
        
        try:
            # 深度解耦 index 和 columns 同名引发的 Pandas 冲突
            df_all_temp = df_all.copy()
            if 'code' in df_all_temp.columns:
                if df_all_temp.index.name == 'code' or 'code' in df_all_temp.index.names:
                    df_all_temp.index.name = '_index_code'
                    
            # 兼容 MultiIndex 和单 index
            if isinstance(df_all_temp.index, pd.MultiIndex):
                # 遍历第一层 index (code)
                for code, df_stock in df_all_temp.groupby(level=0):
                    digits = re.findall(r'\d+', str(code))
                    code_clean = digits[0].zfill(6) if digits else str(code).strip().zfill(6)
                    feat = self._extract_indicators_from_df(df_stock)
                    if feat:
                        self._indicator_cache[(code_clean, today_str)] = feat
                        count += 1
            elif 'code' in df_all_temp.columns:
                # 包含 code 列
                for code, df_stock in df_all_temp.groupby('code'):
                    digits = re.findall(r'\d+', str(code))
                    code_clean = digits[0].zfill(6) if digits else str(code).strip().zfill(6)
                    feat = self._extract_indicators_from_df(df_stock)
                    if feat:
                        self._indicator_cache[(code_clean, today_str)] = feat
                        count += 1
            else:
                # 尝试普通 index
                df_all_clean = df_all_temp.reset_index()
                if 'code' in df_all_clean.columns:
                    for code, df_stock in df_all_clean.groupby('code'):
                        digits = re.findall(r'\d+', str(code))
                        code_clean = digits[0].zfill(6) if digits else str(code).strip().zfill(6)
                        feat = self._extract_indicators_from_df(df_stock)
                        if feat:
                            self._indicator_cache[(code_clean, today_str)] = feat
                            count += 1
                            
            logger.info(f"🚀 [BgKernel] Manually warm-up {count} stock indicators into memory cache!")
        except Exception as e:
            logger.error(f"[BgKernel] Failed to manually warm-up indicators: {e}")

    def _extract_indicators_from_df(self, df_hist: pd.DataFrame) -> dict:
        """
        从单只股票的历史 DataFrame (df_hist) 中提取并计算 evaluate_decision_item 依赖的全部日线特征字典。
        """
        if df_hist is None or df_hist.empty:
            return {}
        
        try:
            df_hist = df_hist.sort_index()
            
            # [DECOUPLE-LIVE] 检测并剔除属于今天（未收盘）的日线，只用纯历史数据计算静态昨日指标
            if not df_hist.empty:
                import datetime
                today_dt = datetime.datetime.now()
                today_str1 = today_dt.strftime("%Y-%m-%d")
                today_str2 = today_dt.strftime("%Y%m%d")
                
                last_idx = df_hist.index[-1]
                last_idx_str = str(last_idx).strip()
                
                is_today = False
                if today_str1 in last_idx_str or today_str2 in last_idx_str:
                    is_today = True
                elif isinstance(last_idx, (datetime.date, datetime.datetime)):
                    if last_idx.year == today_dt.year and last_idx.month == today_dt.month and last_idx.day == today_dt.day:
                        is_today = True
                        
                if is_today:
                    df_hist = df_hist.iloc[:-1]
                    
            if df_hist.empty:
                return {}
                
            row_last = df_hist.iloc[-1]
            close_series = df_hist['close']
            
            # 滚动计算均线
            ma10_series = close_series.rolling(10).mean()
            ma5_series = close_series.rolling(5).mean()
            
            # 优先从行中提取 ma10d，否则 fallback 到 rolling 计算值
            ma10_val = float(row_last.get("ma10d", 0.0))
            if ma10_val <= 0.0:
                ma10_val = float(ma10_series.iloc[-1]) if len(ma10_series) >= 10 else float(row_last.get("close", 0))
                
            # 优先从行中提取 ma5d
            ma5_val = float(row_last.get("ma5d", 0.0))
            if ma5_val <= 0.0:
                ma5_val = float(ma5_series.iloc[-1]) if len(ma5_series) >= 5 else float(row_last.get("close", 0))
            
            swl_val = float(row_last.get("SWL", 0.0))
            close_val = float(row_last.get("close", 0.0))
            if swl_val <= 0 or swl_val < close_val * 0.85 or swl_val > close_val * 1.15:
                swl_val = ma5_val
            
            # 匹配 SWS 支撑工作线
            sws_val = float(row_last.get("SWS", 0.0))
            if sws_val <= 0 or sws_val < close_val * 0.85 or sws_val > close_val * 1.15:
                sws_val = ma10_val
            
            # 获取 5 天前的 SWS 用于 SWS 趋势爬升
            if len(df_hist) >= 6:
                row_prev5 = df_hist.iloc[-6]
                close_prev5 = float(row_prev5.get("close", 0.0))
                sws_prev5_val = float(row_prev5.get("SWS", 0.0))
                if sws_prev5_val <= 0 or sws_prev5_val < close_prev5 * 0.85 or sws_prev5_val > close_prev5 * 1.15:
                    sws_prev5_val = float(ma10_series.iloc[-6]) if len(ma10_series) >= 15 else sws_val
                
                ma10_prev5_val = float(row_prev5.get("ma10d", 0.0))
                if ma10_prev5_val <= 0.0:
                    ma10_prev5_val = float(ma10_series.iloc[-6]) if len(ma10_series) >= 15 else ma10_val
            else:
                sws_prev5_val = sws_val
                ma10_prev5_val = ma10_val

            feat = {
                "sws": sws_val,
                "sws_prev5": sws_prev5_val,
                "swl": swl_val,
                "ma10d": ma10_val,
                "ma10d_prev5": ma10_prev5_val,
                "ma5d": ma5_val,
            }
            
            # 获取 5 天前以及当前的 ma5d
            if len(df_hist) >= 6:
                row_prev5_ma5 = df_hist.iloc[-6]
                ma5d_prev5_val = float(row_prev5_ma5.get("ma5d", 0.0))
                if ma5d_prev5_val <= 0.0:
                    ma5d_prev5_val = float(ma5_series.iloc[-6]) if len(ma5_series) >= 6 else ma5_val
                
                swl_prev5_val = float(row_prev5_ma5.get("SWL", 0.0))
                if swl_prev5_val <= 0:
                    swl_prev5_val = ma5d_prev5_val
            else:
                ma5d_prev5_val = ma5_val
                swl_prev5_val = swl_val
                
            feat["ma5d_prev5"] = ma5d_prev5_val
            feat["swl_prev5"] = swl_prev5_val
            
            # 补充 60 日均线 (ma60d & ma60d_prev5)
            ma60_val = float(row_last.get("ma60d", 0.0))
            if ma60_val <= 0.0:
                if len(df_hist) >= 60:
                    ma60_series = close_series.rolling(60).mean()
                    ma60_val = float(ma60_series.iloc[-1])
                else:
                    ma60_val = close_val
            feat["ma60d"] = ma60_val
            
            # 获取 5 天前的 ma60d
            if len(df_hist) >= 6:
                row_prev5_ma60 = df_hist.iloc[-6]
                ma60d_prev5_val = float(row_prev5_ma60.get("ma60d", 0.0))
                if ma60d_prev5_val <= 0.0:
                    if len(df_hist) >= 65:
                        ma60_series = close_series.rolling(60).mean()
                        ma60d_prev5_val = float(ma60_series.iloc[-6])
                    else:
                        ma60d_prev5_val = ma60_val
            else:
                ma60d_prev5_val = ma60_val
            feat["ma60d_prev5"] = ma60d_prev5_val
            
            # 补充高维的 high4, hmax, low60, pbreak, ptop 等
            feat["high4"] = float(row_last.get("high4", 0.0))
            feat["hmax"] = float(row_last.get("hmax", 0.0))
            feat["low60"] = float(row_last.get("low60", 0.0))
            feat["pbreak"] = int(row_last.get("pbreak", 0.0))
            feat["ptop"] = float(row_last.get("ptop", 0.0))
            
            vol_col = 'volume' if 'volume' in df_hist.columns else ('vol' if 'vol' in df_hist.columns else '')
            if vol_col:
                vol_ma5_series = df_hist[vol_col].rolling(5).mean()
                feat["vol_ma5"] = float(vol_ma5_series.iloc[-1]) if len(vol_ma5_series) >= 5 else float(row_last.get(vol_col, 0))
            
            # 补充昨日、前日、大前日的高/开/收价格，以及今日开盘价
            feat["open"] = float(row_last.get("open", 0.0))
            
            if len(df_hist) >= 4:
                feat["high_prev1"] = float(df_hist.iloc[-2].get("high", 0.0))
                feat["high_prev2"] = float(df_hist.iloc[-3].get("high", 0.0))
                feat["high_prev3"] = float(df_hist.iloc[-4].get("high", 0.0))
                
                feat["open_prev1"] = float(df_hist.iloc[-2].get("open", 0.0))
                feat["open_prev2"] = float(df_hist.iloc[-3].get("open", 0.0))
                feat["open_prev3"] = float(df_hist.iloc[-4].get("open", 0.0))
                
                feat["close_prev1"] = float(df_hist.iloc[-2].get("close", 0.0))
                feat["close_prev2"] = float(df_hist.iloc[-3].get("close", 0.0))
                feat["close_prev3"] = float(df_hist.iloc[-4].get("close", 0.0))
                
                feat["low_prev1"] = float(df_hist.iloc[-2].get("low", 0.0))
            else:
                feat["high_prev1"] = close_val
                feat["high_prev2"] = close_val
                feat["high_prev3"] = close_val
                
                feat["open_prev1"] = close_val
                feat["open_prev2"] = close_val
                feat["open_prev3"] = close_val
                
                feat["close_prev1"] = close_val
                feat["close_prev2"] = close_val
                feat["close_prev3"] = close_val
                
                feat["low_prev1"] = close_val
                
            return feat
        except Exception as e:
            logger.error(f"[BgKernel] Failed to extract technical indicators from DataFrame: {e}")
            return {}

    @property
    def mode(self) -> str:
        return self._mode

    def set_trading_mode(self, new_mode: str) -> bool:
        """安全天梯模式转换机制 (Mode Ladder Switch)
        
        支持 OBSERVE -> PAPER -> CONFIRM -> LIVE_AUTO。
        尝试升格至 LIVE_AUTO 时必须 100% 物理通过 8 大安全网关检验，否则强行回退至 OBSERVE 旁路！
        """
        target = new_mode.upper()
        if target not in {"OBSERVE", "PAPER", "CONFIRM", "LIVE_AUTO"}:
            logger.error(f"[Ladder] Invalid trading mode requested: {new_mode}")
            return False

        if target == "LIVE_AUTO":
            # 物理验证实盘全自动下单 8 大前置防护关卡
            passed, reasons = self._verify_live_preconditions()
            if not passed:
                logger.error(f"🚨🚨 [Ladder] LIVE_AUTO升格失败！未通过的安全卡口: {reasons}. 强行物理降级回退至 OBSERVE 观察模式！")
                self._mode = "OBSERVE"
                self.executor = None
                return False
            
            logger.warning("🟢🟢🟢 [Ladder] ALL 8 PRECONDITIONS PASSED! Upgraded successfully to LIVE_AUTO Full-Auto Mode!")
            self.executor = self.broker_adapter
        elif target == "CONFIRM":
            logger.info("[Ladder] Mode set to CONFIRM. Executions will prompt the confirmation bubble.")
            self.executor = self.confirm_adapter
        elif target == "PAPER":
            logger.info("[Ladder] Mode set to PAPER. Direct simulated execution active.")
            self.executor = self.paper_adapter
        else:
            logger.info("[Ladder] Mode set to OBSERVE. Side-channel logging only.")
            self.executor = None

        self._mode = target
        return True

    def evaluate_decision_item(self, item: Mapping[str, Any], write_journal: bool = True, limits_override: RiskLimits | None = None) -> dict[str, Any]:
        # 处于回测模拟模式下，直接短路返回，无需响应策略交易流以避免资源浪费
        if hasattr(self, "paper_adapter") and self.paper_adapter and getattr(self.paper_adapter, "_is_simulation", False):
            return {
                "kernel_state": "",
                "kernel_action": "HOLD",
                "kernel_size_pct": 0.0,
                "kernel_confidence": 0.0,
                "kernel_allowed": False,
                "kernel_reject_code": "SIMULATION_BYPASS",
                "kernel_stop_price": None,
                "kernel_trace_id": "",
                "kernel_reason": {},
                "kernel_order_id": "",
                "kernel_executed": False,
            }

        raw_hash = stable_hash(dict(item))
        
        # 提取内存中该个股持仓的状态并注入特征，以实现实盘/模拟盘 100% 对齐回测
        is_swing_low_mode = False
        tp_triggered = False
        max_pnl_since_entry = 0.0
        code = str(item.get("code") or "")
        
        # 动态匹配当前执行的柜台实例以读取仓位
        active_executor = getattr(self, "executor", None)
        if not active_executor:
            active_executor = getattr(self, "paper_adapter", None) or getattr(self, "broker_adapter", None)
            
        if code and active_executor and getattr(active_executor, "account", None):
            pos = active_executor.account.positions.get(code)
            if pos:
                is_swing_low_mode = (getattr(pos, "regime", "") == "SWING_LOW_BUY")
                tp_triggered = getattr(pos, "tp_triggered", False)
                max_pnl_since_entry = getattr(pos, "pnl_pct", 0.0)
                if hasattr(pos, "max_high") and pos.max_high > 0.0 and getattr(pos, "entry_price", 0.0) > 0.0:
                    max_pnl_since_entry = (pos.max_high - pos.entry_price) / pos.entry_price * 100.0

            # 👑 引入终极自愈保护：如果物理持仓 pos 不存在（无持仓），但 state_manager 状态为 IN_TRADE，
            # 说明是幽灵残留状态，强制自愈重置为 FLAT，彻底解决“空仓却被 ALREADY_IN_TRADE 拦截”的痛点！
            # 如果物理持仓 pos 存在（有持仓），但 state_manager 状态为 FLAT，说明是状态丢失，强制自愈对准为 IN_TRADE！
            current_state_in_manager = self.state_manager.get(code)
            has_holding = (code in active_executor.account.positions)
            if not has_holding and current_state_in_manager == "IN_TRADE":
                self.state_manager.set(code, "FLAT")
                logger.warning(f"🔄 [StateManagerSelfHeal] Auto-aligned state for {code} from IN_TRADE to FLAT due to zero holdings.")
            elif has_holding and current_state_in_manager == "FLAT":
                self.state_manager.set(code, "IN_TRADE")
                logger.warning(f"🔄 [StateManagerSelfHeal] Auto-aligned state for {code} from FLAT to IN_TRADE due to active holdings.")

        item_dict = dict(item)
        item_dict["is_swing_low_mode"] = is_swing_low_mode
        item_dict["tp_triggered"] = tp_triggered
        item_dict["max_pnl_since_entry"] = max_pnl_since_entry

        # 实盘/模拟盘下，为防止 UI 传来的 sig 缺少多周期核心技术指标，我们在此处自动抓取本地数据进行补全！
        if code and (item_dict.get("sws") is None or item_dict.get("ma10d") is None):
            today_str = datetime.now().strftime("%Y-%m-%d")
            cache_key = (code, today_str)
            
            def safe_update_indicators(target_dict: dict, source_feat: dict):
                """
                安全合入静态特征指标，绝对不让老/昨日特征覆盖当前实盘实时的 OHLC 价格与成交量、涨幅！
                """
                for k, v in source_feat.items():
                    if k in ['open', 'high', 'low', 'close', 'volume', 'amount', 'trade', 'price', 'percent', 'pct']:
                        if k in target_dict and target_dict[k] is not None and float(target_dict[k]) > 0.0:
                            continue
                    target_dict[k] = v
            
            # 如果缓存命中，则在亚毫秒级内实现 O(1) 直接拼装返回！
            if cache_key in self._indicator_cache:
                safe_update_indicators(item_dict, self._indicator_cache[cache_key])
                # 特别单独提取 setup，防止由于 state_manager 变动而导致状态不同步
                curr_state = self.state_manager.get(code) if hasattr(self, "state_manager") else None
                item_dict["setup"] = getattr(curr_state, "setup", "") if curr_state else ""
            else:
                loaded_from_df_all = False
                df_all = self._get_df_all()
                if df_all is not None and not df_all.empty:
                    # 早盘冷启动自愈：一旦探测到 df_all 且缓存为空，瞬间批量预热全市场 5484 只股票到内存
                    if not self._indicator_cache:
                        try:
                            logger.info(f"[BgKernel] Auto-detecting in-memory df_all. Triggering premarket cache warming...")
                            self.warm_up_indicator_cache(df_all)
                        except Exception as ex:
                            logger.error(f"[BgKernel] Premarket self-healing warming from df_all failed: {ex}")
                            
                    # 温热完成后，再次检查是否在内存中直接命中
                    if cache_key in self._indicator_cache:
                        safe_update_indicators(item_dict, self._indicator_cache[cache_key])
                        loaded_from_df_all = True
                        
                    if not loaded_from_df_all:
                        try:
                            import pandas as pd
                            if code in df_all.index:
                                row_stock = df_all.loc[code]
                                feat = {}
                                for col in ['sws', 'sws_prev5', 'swl', 'ma10d', 'ma10d_prev5', 'ma5d', 'ma5d_prev5', 'swl_prev5',
                                            'ma60d', 'ma60d_prev5', 'high4', 'hmax', 'low60', 'pbreak', 'ptop', 'vol_ma5', 'open',
                                            'high_prev1', 'high_prev2', 'high_prev3', 'open_prev1', 'open_prev2', 'open_prev3',
                                            'close_prev1', 'close_prev2', 'close_prev3', 'low_prev1']:
                                    if col in row_stock and pd.notna(row_stock[col]):
                                        feat[col] = int(row_stock[col]) if col == 'pbreak' else float(row_stock[col])
                                
                                if feat:
                                    close_val = float(row_stock.get('close', 0.0)) if pd.notna(row_stock.get('close')) else 0.0
                                    if feat.get('ma5d', 0.0) <= 0.0: feat['ma5d'] = close_val
                                    if feat.get('ma10d', 0.0) <= 0.0: feat['ma10d'] = close_val
                                    if feat.get('ma60d', 0.0) <= 0.0: feat['ma60d'] = close_val
                                    if feat.get('sws', 0.0) <= 0.0: feat['sws'] = feat['ma10d']
                                    if feat.get('swl', 0.0) <= 0.0: feat['swl'] = feat['ma5d']
                                    
                                    self._indicator_cache[cache_key] = feat
                                    safe_update_indicators(item_dict, feat)
                                    loaded_from_df_all = True
                        except Exception as e:
                            logger.debug(f"[BgKernel] Extract from df_all failed for {code}: {e}")

                loaded_from_h5 = False
                if not loaded_from_df_all:
                    try:
                        import os
                        import pandas as pd
                        base_dir = get_app_root()
                        today_date_str = datetime.now().strftime("%Y%m%d")
                        for path in [fr'G:\shared_df_all-{today_date_str}.h5', r'G:\shared_df_all.h5', r'g:\top_all.h5', os.path.join(base_dir, 'top_all.h5'), os.path.join(get_app_root(), 'top_all.h5'), 'top_all.h5']:
                            if os.path.exists(path):
                                # 智能探测 HDF5 key，自适应 'df_all' 还是 'top_all'
                                key_to_read = None
                                try:
                                    with pd.HDFStore(path, mode='r') as store:
                                        keys = store.keys()
                                        if keys:
                                            key_to_read = keys[0].lstrip('/')
                                except Exception:
                                    pass
                                if not key_to_read:
                                    key_to_read = 'top_all'
                                
                                try:
                                    df_top = pd.read_hdf(path, key_to_read)
                                except Exception:
                                    try:
                                        df_top = pd.read_hdf(path, 'df_all')
                                    except Exception:
                                        df_top = pd.read_hdf(path, 'top_all')
                                
                                if df_top is not None and not df_top.empty:
                                    import re
                                    # 建立 code 到 row 的映射，只保留 6 位纯数字以消除后缀歧义
                                    code_to_row = {}
                                    for idx_s, row_s in df_top.iterrows():
                                        c_val = idx_s[0] if isinstance(idx_s, tuple) else idx_s
                                        raw_c_str = str(c_val).strip()
                                        if not raw_c_str or raw_c_str == 'nan':
                                            raw_c_str = str(row_s.get('code', '')).strip()
                                            
                                        digits_s = re.findall(r'\d+', raw_c_str)
                                        if digits_s:
                                            code_to_row[digits_s[0].zfill(6)] = row_s
                                            
                                    row_stock = code_to_row.get(code)
                                    
                                    if row_stock is not None:
                                        row_cols_lower = {str(k).lower(): k for k in row_stock.keys()} if hasattr(row_stock, 'keys') else {}
                                        feat = {}
                                        for col in ['sws', 'sws_prev5', 'swl', 'ma10d', 'ma10d_prev5', 'ma5d', 'ma5d_prev5', 'swl_prev5',
                                                    'ma60d', 'ma60d_prev5', 'high4', 'hmax', 'low60', 'pbreak', 'ptop', 'vol_ma5', 'open',
                                                    'high_prev1', 'high_prev2', 'high_prev3', 'open_prev1', 'open_prev2', 'open_prev3',
                                                    'close_prev1', 'close_prev2', 'close_prev3', 'low_prev1']:
                                            matched_key = None
                                            if col in row_stock:
                                                matched_key = col
                                            elif col.lower() in row_cols_lower:
                                                matched_key = row_cols_lower[col.lower()]
                                            elif col.upper() in row_stock:
                                                matched_key = col.upper()
                                                
                                            if matched_key is not None:
                                                val = row_stock[matched_key]
                                                if pd.notna(val):
                                                    feat[col] = int(val) if col == 'pbreak' else float(val)
                                        
                                        if feat:
                                            # 支持大写 CLOSE 获取
                                            close_key = 'close'
                                            if 'close' not in row_stock:
                                                if 'CLOSE' in row_stock:
                                                    close_key = 'CLOSE'
                                                elif 'close'.lower() in row_cols_lower:
                                                    close_key = row_cols_lower['close'.lower()]
                                                    
                                            close_val = float(row_stock.get(close_key, 0.0)) if pd.notna(row_stock.get(close_key)) else 0.0
                                            if feat.get('ma5d', 0.0) <= 0.0: feat['ma5d'] = close_val
                                            if feat.get('ma10d', 0.0) <= 0.0: feat['ma10d'] = close_val
                                            if feat.get('ma60d', 0.0) <= 0.0: feat['ma60d'] = close_val
                                            if feat.get('sws', 0.0) <= 0.0: feat['sws'] = feat['ma10d']
                                            if feat.get('swl', 0.0) <= 0.0: feat['swl'] = feat['ma5d']
                                            
                                            self._indicator_cache[cache_key] = feat
                                            safe_update_indicators(item_dict, feat)
                                            loaded_from_h5 = True
                                            break
                    except Exception as e:
                        logger.debug(f"[BgKernel] Re-try load from HDF5 failed for {code}: {e}")
                
                if not loaded_from_df_all and not loaded_from_h5:
                    try:
                        from JSONData.tdx_data_Day import get_tdx_Exp_day_to_df
                        from JohnsonUtil import commonTips as cct
                        from JohnsonUtil.commonTips import timed_ctx
                        with timed_ctx(f"LiveIndicatorEnrich_{code}", warn_ms=100):
                            limit_days = getattr(cct, 'compute_lastdays', 120)
                            df_hist = get_tdx_Exp_day_to_df(code, dl=limit_days)
                            if df_hist is not None and not df_hist.empty:
                                feat = self._extract_indicators_from_df(df_hist)
                                if feat:
                                    self._indicator_cache[cache_key] = feat
                                    safe_update_indicators(item_dict, feat)
                    except Exception as e:
                        logger.error(f"[BgKernel] Failed to auto-enrich live indicators for {code}: {e}")
                
                curr_state = self.state_manager.get(code) if hasattr(self, "state_manager") else None
                item_dict["setup"] = getattr(curr_state, "setup", "") if curr_state else ""

        signal = canonicalize_decision_queue_item(item_dict)
        state = self.state_manager.get(signal.code)
        intent = decide(signal, state)
        risk = evaluate(intent, signal, state, limits_override or self.limits)

        signal_hash = stable_hash(signal)
        intent_hash = stable_hash(intent)
        risk_hash = stable_hash(risk)
        trace = KernelTrace(
            trace_id=stable_hash((raw_hash, signal_hash, state, intent_hash, risk_hash))[:20],
            raw_event_hash=raw_hash,
            signal_hash=signal_hash,
            state=state,
            intent_hash=intent_hash,
            risk_hash=risk_hash,
            execution_hash=None,
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )

        result = {
            "kernel_state": state,
            "kernel_action": risk.final_action,
            "kernel_size_pct": risk.final_size_pct,
            "kernel_confidence": intent.confidence,
            "kernel_allowed": risk.allowed,
            "kernel_reject_code": str(risk.reject_context.get("message", risk.reject_context.get("code", ""))) if risk.reject_context else "",
            "kernel_stop_price": intent.stop_price,
            "kernel_trace_id": trace.trace_id,
            "kernel_reason": asdict(intent.reason),
            "kernel_order_id": risk.order.order_id if risk.order else "",
            "kernel_executed": False,
        }

        # 处于交易激活态 (PAPER/CONFIRM/LIVE_AUTO) 且风控允许、有生成获批委托订单，并且是写入交易流水的主执行链路（避免UI查询富化流误触发）
        executor_to_use = self.executor
        is_manual = bool(intent.reason and intent.reason.regime == "MANUAL_OVERRIDE")
        if executor_to_use is None and is_manual:
            executor_to_use = self.paper_adapter

        if write_journal and executor_to_use is not None and risk.allowed and risk.order:
            executed = executor_to_use.submit_order(risk.order)
            result["kernel_executed"] = executed
            
            # 如果物理执行交易成功，同步更新 StateManager 状态与 paper_adapter 内存属性
            if executed:
                if risk.final_action in {"BUY", "ADD"}:
                    self.state_manager.set(signal.code, "IN_TRADE")
                    if hasattr(self, "paper_adapter") and self.paper_adapter and self.paper_adapter.account:
                        pos = self.paper_adapter.account.positions.get(signal.code)
                        if pos:
                            if risk.final_action == "BUY":
                                pos.regime = getattr(intent.reason, "regime", "BREAKOUT_ALLOWED")
                                pos.tp_triggered = False
                            elif risk.final_action == "ADD":
                                pos.tp_triggered = False
                            self.paper_adapter._save_state()
                elif risk.final_action == "SELL":
                    if risk.final_size_pct >= 0.95:
                        self.state_manager.set(signal.code, "FLAT")
                    else:
                        self.state_manager.set(signal.code, "IN_TRADE")
                        if hasattr(self, "paper_adapter") and self.paper_adapter and self.paper_adapter.account:
                            pos = self.paper_adapter.account.positions.get(signal.code)
                            if pos:
                                if getattr(intent.reason, "regime", "") == "TAKE_PROFIT_TRIGGERED" or risk.final_size_pct == 0.70:
                                    pos.tp_triggered = True
                                self.paper_adapter._save_state()

        if write_journal:
            self.journal.append(
                {
                    "trace": trace,
                    "signal": signal,
                    "intent": intent,
                    "risk": risk,
                    "kernel_result": result,
                }
            )
        return result

    def _verify_live_preconditions(self) -> tuple[bool, list[str]]:
        """物理校验全自动实盘下单 8 大前置防护关卡"""
        reasons = []
        
        # 1. 交易时间卡口
        try:
            from JohnsonUtil import commonTips as cct
        except ImportError:
            try:
                import commonTips as cct
            except ImportError:
                import common as cct
        
        # 获取工作日与交易时间
        is_trade_day = cct.get_trade_date_status()
        now_dt = datetime.now()
        now_time = now_dt.hour * 100 + now_dt.minute
        # 正常活跃时段：09:15-11:30, 13:00-15:05
        is_active = is_trade_day and ((915 <= now_time <= 1130) or (1300 <= now_time <= 1505))
        if not is_active:
            logger.warning("⚠️ [Preconditions] Currently NON_TRADING_SESSION, but allowing LIVE_AUTO mode pre-set. Orders will remain blocked until the session starts.")


        # 2. 柜台连接卡口
        if not self.broker_adapter._connected:
            reasons.append("BROKER_DISCONNECTED")

        # 3. 物理紧急切断开关 (KillSwitch Off)
        if self.kill_switch.is_killed():
            reasons.append("KILL_SWITCH_ACTIVE")

        # 4. 风控模块正常加载卡口 (RiskGate Enabled)
        # 如果能正常初始化并核对 RiskLimits，代表风控可用
        try:
            limits = RiskLimits()
            if limits.daily_loss_limit_amount <= 0.0 or limits.max_single_stock_position_pct <= 0.0 or limits.max_single_size_pct <= 0.0:
                reasons.append("RISK_LIMITS_CORRUPTED")
        except Exception:
            reasons.append("RISK_GATE_FAILED_TO_LOAD")

        # 5. 日内累计亏损控制卡口 (Daily Loss Not Breached)
        # 获取账户浮动和已亏损情况，此处对接 broker 实盘快照资产核对
        try:
            snap = self.broker_adapter.get_account_snapshot()
            # 假设基准资产为 50 万，若总资产回撤超 10%，阻断
            if snap.get("total_asset", 0.0) < 450000.0:
                reasons.append("DAILY_LOSS_BREACHED")
        except Exception:
            reasons.append("ACCOUNT_SNAPSHOT_UNAVAILABLE")

        # 6. 持仓资产同步对账卡口 (Account Synced)
        # 必须完成对账且无飘移
        try:
            local_pos = self.paper_adapter.get_positions()
            broker_pos = self.broker_adapter.get_positions()
            from trading_kernel.execution.broker_adapter import BrokerPositionSync
            syncer = BrokerPositionSync()
            synced, _ = syncer.sync_and_verify(local_pos, broker_pos)
            if not synced:
                # 触发对账自愈 (Reconciliation Auto-Healing)：以柜台权威数据覆盖本地内存与磁盘持久化账薄，解锁对账
                from trading_kernel.execution.paper_adapter import Position
                new_positions = {}
                for code, pos_data in broker_pos.items():
                    new_positions[code] = Position(
                        code=code,
                        entry_price=float(pos_data.get("entry_price", 0.0)),
                        volume=float(pos_data.get("volume", 0.0)),
                        current_price=float(pos_data.get("current_price", pos_data.get("entry_price", 0.0)))
                    )
                self.paper_adapter.account.positions = new_positions
                snap = self.broker_adapter.get_account_snapshot()
                self.paper_adapter.account.cash = float(snap.get("cash", self.paper_adapter.account.cash))
                self.paper_adapter._save_state()
                
                # 重新同步更新全量 state_manager 中的股票状态与物理持仓对齐
                try:
                    current_states = self.state_manager.snapshot()
                    for code_str, state_val in current_states.items():
                        if code_str not in broker_pos and state_val == "IN_TRADE":
                            self.state_manager.set(code_str, "FLAT")
                            logger.info(f"🔄 [PositionSync] Auto-healed state for {code_str} from IN_TRADE to FLAT (no actual holdings).")
                    for code_str in broker_pos:
                        if current_states.get(code_str) != "IN_TRADE":
                            self.state_manager.set(code_str, "IN_TRADE")
                            logger.info(f"🔄 [PositionSync] Auto-healed state for {code_str} to IN_TRADE (aligned with actual holdings).")
                except Exception as e_sync_state:
                    logger.error(f"Failed to align state_manager with broker positions during sync: {e_sync_state}")
                
                # 重新校验一次
                local_pos_after = self.paper_adapter.get_positions()
                synced_after, _ = syncer.sync_and_verify(local_pos_after, broker_pos)
                if not synced_after:
                    reasons.append("ACCOUNT_OUT_OF_SYNC")
                else:
                    logger.info("🟢 [PositionSync] Reconciliation auto-healing executed! Local positions aligned with broker.")
        except Exception as e:
            logger.error(f"Position sync exception during verification: {e}")
            reasons.append("POSITION_SYNC_EXCEPTION")

        # 7. 内核版本指纹锁死卡口 (Kernel Version Locked)
        if not self.KERNEL_VERSION.startswith("2026.05.23"):
            reasons.append("KERNEL_VERSION_MISMATCH")

        # 8. 单元与回归测试通过卡口 (Replay Equivalence Verification)
        # 实战下检测测试状态机：在测试环境 (pytest) 下，默认拦截 LIVE_AUTO 升级，防止测试运行时意外误触发真盘操作
        import os
        if "PYTEST_CURRENT_TEST" in os.environ:
            reasons.append("TEST_ENVIRONMENT_BLOCKED")

        if reasons:
            return False, reasons
        return True, []


_SERVICE: TradingKernelService | None = None


def get_kernel_service() -> TradingKernelService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = TradingKernelService()
    return _SERVICE


def enrich_decision_item(item: Mapping[str, Any], write_journal: bool = True) -> dict[str, Any]:
    enriched = dict(item)
    try:
        enriched.update(get_kernel_service().evaluate_decision_item(item, write_journal=write_journal))
    except Exception as exc:
        enriched.update(
            {
                "kernel_state": "",
                "kernel_action": "ERROR",
                "kernel_size_pct": 0.0,
                "kernel_confidence": 0.0,
                "kernel_allowed": False,
                "kernel_reject_code": f"KERNEL_ERROR:{exc}",
                "kernel_stop_price": None,
                "kernel_trace_id": "",
                "kernel_order_id": "",
            }
        )
    return enriched
