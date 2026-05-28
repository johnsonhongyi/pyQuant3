import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Tuple

logger = logging.getLogger("ReentryTracker")

# 观察期默认 5 天
OBSERVATION_DAYS = 5

class ReentryWatchItem:
    def __init__(self, code: str, stop_price: float, exit_time: str = None, lowest_since_exit: float = None, status: str = "OBSERVING"):
        self.code = code
        self.stop_price = float(stop_price)
        self.exit_time = exit_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.lowest_since_exit = float(lowest_since_exit if lowest_since_exit is not None else stop_price)
        self.status = status # OBSERVING, ACTIVATED, EXPIRED

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "stop_price": self.stop_price,
            "exit_time": self.exit_time,
            "lowest_since_exit": self.lowest_since_exit,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ReentryWatchItem":
        return cls(
            code=d["code"],
            stop_price=d["stop_price"],
            exit_time=d.get("exit_time"),
            lowest_since_exit=d.get("lowest_since_exit"),
            status=d.get("status", "OBSERVING")
        )

class ReentryTracker:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, state_file: str = None):
        if getattr(self, "_initialized", False):
            return
        
        # 定位持久化路径
        if state_file is None:
            # 仿照 stock_standalone 的通用配置路径
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.state_file = os.path.join(base_dir, "logs", "reentry_states.json")
        else:
            self.state_file = state_file

        self.watchlist: Dict[str, ReentryWatchItem] = {}
        self._load_state()
        self._initialized = True

    def _load_state(self):
        """跨会话加载止损股票跟踪池"""
        # 如果是 pytest 测试运行期间，隔离文件写入
        if "PYTEST_CURRENT_TEST" in os.environ:
            return

        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for code, d in data.items():
                        self.watchlist[code] = ReentryWatchItem.from_dict(d)
                logger.info(f"📂 [ReentryTracker] 已加载 {len(self.watchlist)} 个止损二次启动跟踪标的")
        except Exception as e:
            logger.error(f"❌ [ReentryTracker] 载入状态失败: {e}")

    def _save_state(self):
        """原子持久化止损股票池"""
        if "PYTEST_CURRENT_TEST" in os.environ:
            return

        try:
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            temp_file = self.state_file + ".tmp"
            data = {code: item.to_dict() for code, item in self.watchlist.items()}
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_file, self.state_file)
        except Exception as e:
            logger.error(f"❌ [ReentryTracker] 保存状态失败: {e}")

    def register_exit(self, code: str, stop_price: float, exit_time: str = None):
        """当个股被平仓/止损时，注册入 Re-entry 观察矩阵"""
        # 排除非法的 0 价格
        if stop_price <= 0:
            return
        
        self.watchlist[code] = ReentryWatchItem(
            code=code,
            stop_price=stop_price,
            exit_time=exit_time or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            lowest_since_exit=stop_price,
            status="OBSERVING"
        )
        logger.info(f"🎯 [ReentryTracker] {code} 止损离场 (价: {stop_price:.2f}, 时间: {self.watchlist[code].exit_time})，送入二次启动观察矩阵")
        self._save_state()

    def update_price(self, code: str, current_price: float):
        """盘中更新洗盘最低价以进行多周期跟踪"""
        if current_price <= 0:
            return
        
        item = self.watchlist.get(code)
        if item and item.status == "OBSERVING":
            if current_price < item.lowest_since_exit:
                item.lowest_since_exit = current_price
                self._save_state()

    def check_activation(self, code: str, features: dict, current_time_str: str = None) -> Tuple[bool, str, float]:
        """
        全量多周期枢轴右侧共振判定
        返回: (是否激活, 激活原因, 置信度乘数系数)
        """
        item = self.watchlist.get(code)
        if not item or item.status != "OBSERVING":
            return False, "", 1.0

        # 检查是否超出 5 天观察期，若超出则自动淘汰过期
        try:
            def parse_dt(dt_str: str) -> datetime:
                dt_str = dt_str.replace("T", " ")
                if len(dt_str) > 19:
                    dt_str = dt_str[:19]
                return datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")

            exit_dt = parse_dt(item.exit_time)
            curr_dt = parse_dt(current_time_str) if current_time_str else datetime.now()
            if curr_dt - exit_dt > timedelta(days=OBSERVATION_DAYS):
                item.status = "EXPIRED"
                self._save_state()
                logger.info(f"⏳ [ReentryTracker] {code} 超出 {OBSERVATION_DAYS} 天观察期已自动过期淘汰 (离场: {item.exit_time}, 当前: {current_time_str or 'now'})")
                return False, "", 1.0
        except Exception as e:
            logger.warning(f"[ReentryTracker] Expiration check failed: {e}")

        price = float(features.get("close", 0.0))
        if price <= 0:
            return False, "", 1.0

        # 提取底层 TDX 多周期特征（带 fallback 保护）
        high4 = float(features.get("high4", 0.0))
        hmax = float(features.get("hmax", 0.0))
        low60 = float(features.get("low60", 0.0))
        pbreak = int(features.get("pbreak", 0))
        ptop = float(features.get("ptop", 0.0))
        dff = float(features.get("dff", 0.0))
        vol_ratio = float(features.get("vol_ratio_5d", 1.0))

        # 门禁 1: 如果现价低于止损后的洗盘最低点上浮 0.5%，直接认定多头尚未企稳
        if price < item.lowest_since_exit * 1.005:
            return False, "", 1.0

        # --- [右侧模式 A] 突破短线枢轴高点 (快速洗盘突破) ---
        if high4 > 0 and price >= high4 and vol_ratio >= 1.15 and price > item.stop_price:
            boost = 1.25 if dff > 0 else 1.15
            reason = f"🚀 右侧枢轴转强：突破洗盘期4日高点(high4={high4:.2f})且放量"
            item.status = "ACTIVATED"
            self._save_state()
            return True, reason, boost

        # --- [右侧模式 B] 突破月线大阻力天花板或大平台突破 ---
        if (hmax > 0 and price >= hmax) or (pbreak == 1 and ptop > 0 and price >= ptop):
            boost = 1.30
            reason = f"👑 大周期突破激活：超越30日最高点(hmax={hmax:.2f})或大平台(ptop={ptop:.2f})"
            item.status = "ACTIVATED"
            self._save_state()
            return True, reason, boost

        # --- [右侧模式 C] 战略低位筑底企稳 (深蹲起跳) ---
        if low60 > 0 and item.lowest_since_exit <= low60 * 1.03:
            # 确认在60日低位底座上浮 4% 且放量拉升
            if price >= item.lowest_since_exit * 1.04 and vol_ratio >= 1.4:
                boost = 1.20
                reason = f"🌱 战略低位起跳：在60日底位(low60={low60:.2f})附近洗盘筑底企稳并放量拉升"
                item.status = "ACTIVATED"
                self._save_state()
                return True, reason, boost

        return False, "", 1.0

    def remove_code(self, code: str):
        """移除个股跟踪状态"""
        if code in self.watchlist:
            self.watchlist.pop(code)
            self._save_state()

    def clear(self):
        """彻底清空"""
        self.watchlist.clear()
        self._save_state()

# 暴露单例
reentry_tracker = ReentryTracker()
