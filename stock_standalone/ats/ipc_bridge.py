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
import pandas as pd
from sys_utils import get_app_root
from db_utils import SQLiteConnectionManager

class IPCBridge:
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
            conn.settimeout(2.0)
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
                    packet = conn.recv(min(length - len(data), 4096))
                    if not packet:
                        break
                    data += packet
                
                if len(data) == length:
                    payload = pickle.loads(data)
                    if isinstance(payload, tuple) and len(payload) >= 2:
                        cmd, body = payload[0], payload[1]
                        if cmd == 'UPDATE_DF_DATA' and data_callback:
                            data_callback(body)
                        elif cmd == 'SIGNAL' and signal_callback:
                            signal_callback(body)
                        elif cmd == 'SIGNALS' and signal_callback:
                            for item in body:
                                try:
                                    signal_callback(item)
                                except Exception as sig_err:
                                    print(f"[IPCBridge] Error in batched signal callback: {sig_err}")
        except Exception as e:
            pass
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
            # Generate mock equity data if no historical trades exist yet
            days = 30
            dates = pd.date_range(end=pd.Timestamp.now(), periods=days).strftime("%Y%m%d").tolist()
            strat_equity = [initial_capital * (1 + 0.001 * i) for i in range(days)]
            bench_equity = [initial_capital * (1 + 0.0005 * i) for i in range(days)]
            return dates, strat_equity, bench_equity

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
