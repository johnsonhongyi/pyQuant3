# -*- coding: utf-8 -*-
"""
ATS IPC Bridge
Provides read-only access to SQLite databases (trading_signals.db, signal_strategy.db)
for historical signals, transaction flows, and portfolio positions.
"""

import os
import json
import sqlite3
import socket
import threading
import pickle
import struct
from datetime import datetime
import pandas as pd
from sys_utils import get_app_root
from db_utils import SQLiteConnectionManager

class IPCBridge:
    @staticmethod
    def _request_full_baseline():
        from data_utils import send_code_via_pipe, PIPE_NAME_TK
        import logging
        return send_code_via_pipe({
            "cmd": "REQ_FULL_SYNC", "port": 26670,
            "service_name": "ats_terminal", "client_name": "ats_terminal",
            "subscribe": True,
        }, logging.getLogger("ATS_Bridge"), PIPE_NAME_TK)

    def __init__(self):
        # Locate the default trading_signals.db
        self.db_path = os.path.join(get_app_root(), "trading_signals.db")
        if not os.path.exists(self.db_path):
            # Fallback to current directory for local testing
            self.db_path = "./trading_signals.db"
            
        self.db_manager = SQLiteConnectionManager.get_instance(self.db_path)

    def start_realtime_listener(self, port=26670, data_callback=None, signal_callback=None):
        """
        Starts a daemon TCP server thread on the specified port.
        Listens for real-time market data updates or signals from the main process.
        """
        self._listener_running = True
        self.server_socket = None
        
        def listen_loop():
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self.server_socket.bind(('127.0.0.1', port))
                self.server_socket.listen(5)
                print(f"[IPCBridge] Realtime listener server started on 127.0.0.1:{port}")
            except Exception as e:
                print(f"[IPCBridge] Failed to bind realtime server to port {port}: {e}")
                return

            while self._listener_running:
                try:
                    conn, addr = self.server_socket.accept()
                    if not self._listener_running:
                        try:
                            conn.close()
                        except:
                            pass
                        break
                    threading.Thread(target=self._handle_client, args=(conn, data_callback, signal_callback), daemon=True).start()
                except Exception as e:
                    if self._listener_running:
                        print(f"[IPCBridge] accept error: {e}")
                    break
        
        t = threading.Thread(target=listen_loop, daemon=True)
        t.start()
        return t

    def stop_listener(self):
        """
        Stops the realtime socket listener server cleanly by closing the socket.
        """
        self._listener_running = False
        if hasattr(self, 'server_socket') and self.server_socket:
            try:
                self.server_socket.close()
            except Exception as e:
                print(f"[IPCBridge] Error closing server socket: {e}")

    def _handle_client(self, conn, data_callback, signal_callback):
        try:
            conn.settimeout(5.0)
            prefix = conn.recv(4)
            if not prefix:
                return
            
            if prefix == b"DATA":
                len_buf = conn.recv(4)
                if len(len_buf) < 4:
                    return
                length = struct.unpack("!I", len_buf)[0]
                
                data = b""
                while len(data) < length:
                    packet = conn.recv(min(length - len(data), 65536))
                    if not packet:
                        break
                    data += packet
                
                if len(data) == length:
                    payload = pickle.loads(data)
                    if isinstance(payload, tuple) and len(payload) >= 2:
                        cmd, body = payload[0], payload[1]
                        if cmd == 'UPDATE_DF_DATA' and data_callback:
                            # 🚀【全量与增量双模解析】支持 dict 包装协议与裸 DataFrame
                            df_to_deliver = None
                            msg_type = 'UPDATE_DF_ALL'
                            if isinstance(body, dict):
                                msg_type = body.get('type', 'UPDATE_DF_ALL')
                                df_payload = body.get('data')
                            elif isinstance(body, pd.DataFrame):
                                df_payload = body
                            else:
                                df_payload = None

                            if isinstance(df_payload, pd.DataFrame) and not df_payload.empty:
                                try:
                                    # 规范化代码索引
                                    df_norm = df_payload.copy()
                                    if 'code' in df_norm.columns:
                                        df_norm['code'] = df_norm['code'].astype(str).str.strip().str.zfill(6)
                                        df_norm.set_index('code', inplace=True)
                                    else:
                                        df_norm.index = df_norm.index.astype(str).str.strip().str.zfill(6)
                                        df_norm.index.name = 'code'

                                    # 增量合并 vs 全量覆盖
                                    # 冷启动/重连/次日跨日没有全量基线时，绝不能把 diff 当成完整行情。
                                    # 否则 ma20d/ma60d/category 等未变化列会直接缺失，评分层随之退化。
                                    today_str = datetime.now().strftime("%Y-%m-%d")
                                    last_cache_date = getattr(self, '_last_cache_date', None)
                                    is_date_rollover = bool(last_cache_date is not None and last_cache_date != today_str)

                                    if msg_type == 'UPDATE_DF_DIFF' and (
                                        not hasattr(self, '_cached_df')
                                        or self._cached_df is None
                                        or self._cached_df.empty
                                        or is_date_rollover
                                    ):
                                        if is_date_rollover:
                                            self._cached_df = None
                                        try:
                                            self._request_full_baseline()
                                            print(f"[IPCBridge] {'Date rollover' if is_date_rollover else 'Cold-start'} diff rejected; requested UPDATE_DF_ALL baseline")
                                        except Exception:
                                            pass
                                        return
                                    elif msg_type == 'UPDATE_DF_DIFF':
                                        try:
                                            df_diff = df_norm
                                            if isinstance(df_diff.columns, pd.MultiIndex):
                                                new_cols = {}
                                                for col in df_diff.columns:
                                                    if isinstance(col, tuple) and len(col) >= 2:
                                                        base_col, val_type = col[0], col[1]
                                                        if val_type == 'self':
                                                            new_cols[base_col] = df_diff[col]
                                                df_diff = pd.DataFrame(new_cols, index=df_diff.index)

                                            for col in df_diff.columns:
                                                if col not in self._cached_df.columns:
                                                    self._cached_df[col] = df_diff[col]

                                            common_idx = self._cached_df.index.intersection(df_diff.index)
                                            if len(common_idx) > 0:
                                                for col in df_diff.columns:
                                                    if col in self._cached_df.columns:
                                                        try:
                                                            col_data = df_diff.loc[common_idx, col]
                                                            valid_mask = col_data.notna()
                                                            valid_indices = valid_mask[valid_mask].index
                                                            if len(valid_indices) > 0:
                                                                self._cached_df.loc[valid_indices, col] = df_diff.loc[valid_indices, col]
                                                        except Exception as column_err:
                                                            raise ValueError(f"增量列 {col} 合并失败") from column_err

                                            new_idx = df_diff.index.difference(self._cached_df.index)
                                            if len(new_idx) > 0:
                                                self._cached_df = pd.concat([self._cached_df, df_diff.loc[new_idx]])
                                            df_to_deliver = self._cached_df.copy()
                                        except Exception as merge_err:
                                            print(f"[IPCBridge] Diff merge failed; requesting full baseline: {merge_err}")
                                            self._cached_df = None
                                            self._request_full_baseline()
                                            return
                                    else:
                                        self._cached_df = df_norm.copy()
                                        self._last_cache_date = today_str
                                        df_to_deliver = self._cached_df
                                except Exception as preprocess_err:
                                    print(f"[IPCBridge] Background DataFrame preprocess error: {preprocess_err}")
                                    self._cached_df = None
                                    self._request_full_baseline()
                                    return

                            # 立即在后台线程（不受 UI 渲染卡顿影响）告知 TK 停止发送，清除发送状态
                            try:
                                import sys
                                from sys_utils import get_app_root
                                root = get_app_root()
                                if root not in sys.path:
                                    sys.path.insert(0, root)
                                from data_utils import send_code_via_pipe, PIPE_NAME_TK
                                import logging
                                local_logger = logging.getLogger("ATS_Bridge")
                                feedback = {"cmd": "ATS_RECEIVED", "port": 26670}
                                if isinstance(body, dict):
                                    feedback.update(
                                        source_version=body.get('source_version'),
                                        sync_session=body.get('sync_session'),
                                    )
                                send_code_via_pipe(feedback, local_logger, PIPE_NAME_TK)
                            except Exception as pipe_err:
                                pass

                            if df_to_deliver is not None:
                                data_callback(df_to_deliver)
                        elif cmd == 'SIGNAL' and signal_callback:
                            signal_callback(body)
                        elif cmd == 'SIGNALS' and signal_callback:
                            for item in body:
                                try:
                                    signal_callback(item)
                                except Exception as sig_err:
                                    print(f"[IPCBridge] Error in batched signal callback: {sig_err}")
        except Exception as e:
            print(f"[IPCBridge] _handle_client exception: {e}")
        finally:
            try:
                conn.close()
            except:
                pass

    def get_open_positions(self):
        """
        Query currently open positions from trade_records.
        """
        query = """
            SELECT code, name, buy_amount, buy_price, status, resample
            FROM trade_records
            WHERE status = 'OPEN'
        """
        try:
            with self.db_manager.execute_query(query) as cursor:
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                return pd.DataFrame(rows, columns=columns)
        except Exception as e:
            print(f"[IPCBridge] Failed to fetch open positions: {e}")
            return pd.DataFrame()

    def get_closed_positions(self):
        """
        Query closed trade history from trade_records.
        """
        query = """
            SELECT code, name, buy_date, buy_price, buy_amount, sell_date, sell_price, profit, pnl_pct, status, buy_reason
            FROM trade_records
            WHERE status = 'CLOSED'
            ORDER BY sell_date DESC
        """
        try:
            with self.db_manager.execute_query(query) as cursor:
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                return pd.DataFrame(rows, columns=columns)
        except Exception as e:
            print(f"[IPCBridge] Failed to fetch closed positions: {e}")
            return pd.DataFrame()

    def get_all_trade_flows(self):
        """
        Queries all trade activities (buy/sell events).
        """
        query = """
            SELECT id, code, name, buy_date, buy_price, buy_amount, buy_reason, sell_date, sell_price, profit, status, action
            FROM trade_records
            ORDER BY id DESC
        """
        try:
            with self.db_manager.execute_query(query) as cursor:
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                return pd.DataFrame(rows, columns=columns)
        except Exception as e:
            print(f"[IPCBridge] Failed to fetch trade flows: {e}")
            return pd.DataFrame()

    def get_historical_signals(self, limit=1000):
        """
        Query historical decision signals from signal_history.
        """
        query = f"""
            SELECT date, code, name, price, action, position, reason, resample
            FROM signal_history
            ORDER BY date DESC
            LIMIT {limit}
        """
        try:
            with self.db_manager.execute_query(query) as cursor:
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                return pd.DataFrame(rows, columns=columns)
        except Exception as e:
            print(f"[IPCBridge] Failed to fetch signal history: {e}")
            return pd.DataFrame()

    def get_equity_curve_data(self, initial_capital=1000000.0):
        """
        Constructs cumulative equity curve over time based on closed positions
        and available cash.
        """
        closed_df = self.get_closed_positions()
        if closed_df.empty:
            # Empty means empty.  Fabricated curves make strategy validation
            # impossible and can be mistaken for real performance.
            return [], [], []

        # Sort by sell date to calculate running equity
        closed_df = closed_df.sort_values('sell_date')
        
        # Group profit by sell date
        daily_profits = closed_df.groupby('sell_date')['profit'].sum().reset_index()
        
        dates = daily_profits['sell_date'].tolist()
        profits = daily_profits['profit'].tolist()
        
        # Calculate cumulative returns
        strat_equity = []
        current = initial_capital
        for p in profits:
            current += p
            strat_equity.append(current)
            
        # Mock benchmark
        bench_equity = []
        bench_current = initial_capital
        for i in range(len(dates)):
            bench_current += (profits[i] * 0.4) # Benchmark performs 40% of our strategy's daily PnL
            bench_equity.append(bench_current)
            
        return dates, strat_equity, bench_equity
