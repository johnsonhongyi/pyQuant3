from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any
from logger_utils import LoggerFactory

logger = LoggerFactory.getLogger("JsonlJournal")


def _safe_get(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    if hasattr(obj, key):
        return getattr(obj, key)
    if hasattr(obj, "keys") and hasattr(obj, "__getitem__"):
        try:
            return obj[key]
        except Exception:
            pass
    return default


class JsonlJournal:
    def __init__(self, path: str = "logs/trading_kernel_trace.jsonl"):
        # 🛡️ 强制绝对路径化，保证多进程/打包环境下所有账簿消费者与生产者物理定位完全对齐
        import os
        from sys_utils import get_base_path
        if not os.path.isabs(path):
            path = os.path.join(get_base_path(), path)
        self.path = path
        self._lock = threading.Lock()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
            
        # 维护一个当天已记录特征集合，用于精准去重
        self._written_records = set()
        if os.path.exists(self.path) and os.path.getsize(self.path) > 0:
            try:
                today_str = datetime.now().strftime("%Y-%m-%d")
                with open(self.path, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-5000:]  # 快速读取最后 5000 行，提取今日信号防重
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            # 同时检查 journal_ts 或新增的 trade_date
                            ts = data.get("trade_date", "") or data.get("journal_ts", "")
                            if ts and ts.startswith(today_str):
                                sig = data.get("signal", {})
                                code = _safe_get(sig, "code")
                                sig_type = _safe_get(sig, "signal_type")
                                action = data.get("kernel_result", {}).get("kernel_action", "")
                                if code:
                                    is_sim = data.get("is_simulation", False)
                                    c_price = data.get("kernel_result", {}).get("kernel_stop_price") or sig.get("price") or 0.0
                                    try:
                                        c_price = float(c_price)
                                    except Exception:
                                        c_price = 0.0
                                    if is_sim:
                                        self._written_records.add((code, "SIMULATION", c_price))
                                    elif sig_type:
                                        self._written_records.add((code, sig_type, action, c_price))
                        except Exception:
                            continue
            except Exception:
                pass

    def append(self, record: dict[str, Any]) -> None:
        payload = dict(record)
        
        now_dt = datetime.now()
        today_str = now_dt.strftime("%Y-%m-%d")
        iso_ts = now_dt.isoformat(timespec="seconds")
        
        # 统一写入/补全 top-level 关键字段，保障数据 schema 一致性与可追溯性
        payload["trade_date"] = today_str
        payload.setdefault("journal_ts", iso_ts)
        payload.setdefault("timestamp", iso_ts)
        
        # 强制将所有传入的时间戳/流水时间规范化为 YYYY-MM-DDTHH:MM:SS 格式，彻底消除空格与毫秒级别的格式不一致
        for key in ["journal_ts", "timestamp"]:
            if key in payload and isinstance(payload[key], str):
                val = payload[key].replace(" ", "T")
                if len(val) > 19 and "." in val:
                    val = val.split(".")[0]
                payload[key] = val

        # 支持审计类日志（如 HUMAN_CONFIRMATION_AUDIT, POSITION_SYNC_AUDIT）直接写入而不受 code 过滤与去重限制
        jtype = payload.get("journal_type")
        if jtype is not None and "AUDIT" in str(jtype):
            try:
                with self._lock:
                    with open(self.path, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(_to_plain(payload), ensure_ascii=False, sort_keys=True) + "\n")
            except Exception as e:
                try:
                    logger.error(f"❌ [JsonlJournal] Failed to append AUDIT record: {e}")
                except Exception:
                    pass
            return

        sig = payload.get("signal", {})
        code = _safe_get(sig, "code")
        sig_type = _safe_get(sig, "signal_type")
        action = _safe_get(payload.get("kernel_result", {}), "kernel_action", "")

        if not code:
            # 没有股票代码，直接过滤忽略
            return

        # 引入标准交易时间工具 (支持打包及各种环境的 Fallback 级联导入)
        try:
            from JohnsonUtil import commonTips as cct
        except ImportError:
            try:
                import commonTips as cct
            except ImportError:
                import common as cct

        # 计算当前是否在交易活跃期 (交易日且 09:15-11:30 或 13:00-15:05)
        is_trade_day = cct.get_trade_date_status()
        now_time = now_dt.hour * 100 + now_dt.minute
        is_active_trading = is_trade_day and ((915 <= now_time <= 1130) or (1300 <= now_time <= 1505))

        # 提取当前最新价格 (用于细粒度防重，放行有实质价格或止损价格波动的真实数据更新)
        current_price = _safe_get(payload.get("kernel_result", {}), "kernel_stop_price") or _safe_get(sig, "price") or 0.0
        try:
            current_price = float(current_price)
        except Exception:
            current_price = 0.0

        if not is_active_trading:
            # 其余时间执行都是模拟信号，标注 simulation 属性
            payload["is_simulation"] = True
            if "kernel_result" in payload and payload["kernel_result"] is not None:
                if isinstance(payload["kernel_result"], dict):
                    payload["kernel_result"]["is_simulation"] = True
                    if "kernel_reason" in payload["kernel_result"] and isinstance(payload["kernel_result"]["kernel_reason"], dict):
                        payload["kernel_result"]["kernel_reason"]["simulation"] = True

            # 模拟时段去重：同一个 code 且价格完全一致时，才过滤 (限制无用冗余，放行有效现价变化)
            key = (code, "SIMULATION", current_price)
            with self._lock:
                if key in self._written_records:
                    return
                self._written_records.add(key)
        else:
            # 交易活跃期去重：同一个 code，同一个信号类型，同一种动作，同一种价格，只允许记录一次
            if not sig_type:
                return
            key = (code, sig_type, action, current_price)
            with self._lock:
                if key in self._written_records:
                    return
                self._written_records.add(key)

        try:
            trimmed_payload = _trim_record(payload)
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(_to_plain(trimmed_payload), ensure_ascii=False, sort_keys=True) + "\n")
                
                # 每次物理追加新记录后，自动触发高性能日志体积安全监控与压缩归档
                self._check_and_compress_journal()
        except Exception as e:
            try:
                logger.error(f"❌ [JsonlJournal] Failed to append record: {e}")
            except Exception:
                pass

    def _check_and_compress_journal(self) -> None:
        """高性能无损日志自动压缩归档与滚动清理引擎：若日志文件超过 2MB，自动将旧记录打包压缩归档，保留最新 1000 行，且只保留最新的 10 个归档包以防磁盘膨胀"""
        try:
            if not os.path.exists(self.path):
                return
            file_size = os.path.getsize(self.path)
            # 设定 2MB 为阈值 (2 * 1024 * 1024)
            if file_size < 2 * 1024 * 1024:
                return

            import gzip
            
            # 1. 物理读取全部行
            with open(self.path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            if len(lines) <= 1500:
                return
                
            # 保留最近 1000 行作为活流水，确保 UI 载入不白屏
            keep_lines = lines[-1000:]
            archive_lines = lines[:-1000]
            
            # 2. 导出归档历史并生成高压 gzip 文件
            parent_dir = os.path.dirname(self.path)
            archive_dir = os.path.join(parent_dir, "archive")
            if not os.path.exists(archive_dir):
                os.makedirs(archive_dir, exist_ok=True)
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_filename = f"trading_kernel_trace_{timestamp_str}.jsonl.gz"
            archive_path = os.path.join(archive_dir, archive_filename)
            
            with gzip.open(archive_path, "wt", encoding="utf-8") as gz:
                gz.writelines(archive_lines)
                
            # 3. 原子覆写原主日志文件，释放物理磁盘空间，实现完美零损耗压缩
            temp_path = self.path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as tmp:
                tmp.writelines(keep_lines)
                
            os.replace(temp_path, self.path)
            
            # 4. 自动滚动清理历史归档文件，只保留最新的 10 个压缩包
            import glob
            archive_pattern = os.path.join(archive_dir, "trading_kernel_trace_*.jsonl.gz")
            archive_files = glob.glob(archive_pattern)
            # 按修改时间从旧到新排序
            archive_files.sort(key=lambda x: os.path.getmtime(x))
            
            max_archives = 10
            if len(archive_files) > max_archives:
                to_delete = archive_files[:-max_archives]
                for file_to_del in to_delete:
                    try:
                        os.remove(file_to_del)
                    except Exception:
                        pass
            
            try:
                logger.info(f"⚡ [JsonlJournal] Compression and cleanup success! Compressed {len(archive_lines)} lines to {archive_path}. Kept {len(keep_lines)} active lines, total archives capped at {max_archives}.")
            except Exception:
                pass
        except Exception as e_comp:
            try:
                logger.warning(f"⚠️ [JsonlJournal] Failed to compress journal file: {e_comp}")
            except Exception:
                pass


def _to_plain(value: Any) -> Any:
    if is_dataclass(value):
        return _to_plain(asdict(value))
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def _trim_record(rec: dict[str, Any]) -> dict[str, Any]:
    """精炼与裁剪单行交易日志数据，在不影响 UI 渲染与决策回放的前提下剔除冗余调试字段"""
    if not isinstance(rec, dict):
        return rec
    if rec.get("journal_type") == "HUMAN_CONFIRMATION_AUDIT":
        return rec
        
    trimmed = {}
    for k, v in rec.items():
        if k in ("signal", "trace", "intent", "risk", "kernel_result", "kernel_reason"):
            if isinstance(v, dict):
                trimmed[k] = _trim_dict(v)
            else:
                trimmed[k] = v
        else:
            trimmed[k] = v
    return trimmed


def _trim_dict(d: dict[str, Any]) -> dict[str, Any]:
    res = {}
    for k, v in d.items():
        # 1. 过滤冗余的调试字段，这些字段与 UI 渲染及回放重演无因果联系
        if k in ("confidence_inputs",):
            continue
        
        # 2. 如果是嵌套字典，递归处理
        if isinstance(v, dict):
            res[k] = _trim_dict(v)
        elif isinstance(v, list):
            # 缩减过长的列表
            if len(v) > 10:
                res[k] = [_trim_val(x) for x in v[:10]] + ["...truncated..."]
            else:
                res[k] = [_trim_val(x) for x in v]
        else:
            res[k] = _trim_val(v)
    return res


def _trim_val(v: Any) -> Any:
    # 保留高精浮点数，但对冗长的小数进行美化和压缩 (保留 4 位有效小数)
    if isinstance(v, float):
        return round(v, 4)
    return v


