# -*- coding: utf-8 -*-
"""
Created At: 2026-06-26
Description: 通用实时行情数据同步管理器 (Generic Realtime Data Sync Manager)
             封装了底层 TCP Socket 数据监听、协议包反序列化、增量/全量合并以及命名管道同步反馈。
             可跨模块、跨窗口复用，并支持在非 Pandas 环境下的安全降级。
"""
import os
import sys
import time
import socket
import struct
import pickle
import threading
import json

class IPCSyncManager:
    """
    通用实时数据同步管理器，使用跟 ATS / 可视化器一致的协议与主程序通信
    """
    def __init__(self, port=26671, data_callback=None, logger=None):
        self.port = port
        self.data_callback = data_callback
        self.logger = logger
        
        self.current_df = None
        self.df_lock = threading.Lock()
        
        self._listener_running = False
        self.server_socket = None
        self._listener_thread = None
        self._heartbeat_thread = None
        self.last_recv_t = time.time()
        
        self.pipe_name = r'\\.\pipe\instock_tk_pipe'
        
    def log_info(self, msg):
        if self.logger:
            self.logger.info(msg)
        else:
            print(f"[IPCSyncManager] {msg}")

    def log_error(self, msg):
        if self.logger:
            self.logger.error(msg)
        else:
            print(f"[IPCSyncManager] ERROR: {msg}")

    def start(self):
        """开启后台 TCP 监听服务，并向主进程请求初始数据"""
        self._listener_running = True
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()
        
        # 启动心跳探测与自动重连同步线程
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        
        self.log_info(f"启动同步管理器，监听本地端口: {self.port}")

    def stop(self):
        """安全停止监听"""
        self._listener_running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        self.log_info("同步管理器已停止监听")

    def get_current_df(self):
        """线程安全地获取当前同步的行情 DataFrame"""
        with self.df_lock:
            if self.current_df is not None:
                return self.current_df.copy()
            return None

    def request_full_sync(self):
        """通过 Windows 命名管道向主程序发送 REQ_FULL_SYNC，拉取全量行情快照"""
        cmd_dict = {"cmd": "REQ_FULL_SYNC"}
        payload = json.dumps(cmd_dict, ensure_ascii=False).encode("utf-8")
        
        for attempt in range(5):
            try:
                import win32file
                import win32pipe
                import winerror
                import pywintypes
                
                handle = win32file.CreateFile(
                    self.pipe_name, win32file.GENERIC_WRITE, 0, None,
                    win32file.OPEN_EXISTING, 0, None
                )
                win32file.WriteFile(handle, payload)
                win32file.CloseHandle(handle)
                self.log_info(f"成功发送全量同步请求 REQ_FULL_SYNC (第 {attempt+1} 次尝试)")
                return True
            except Exception as e:
                time.sleep(0.5)
        self.log_error("发送全量同步请求 REQ_FULL_SYNC 失败，主程序管道可能未准备就绪")
        return False

    def _heartbeat_loop(self):
        """自动定时心跳，在需要时（冷启动或长时间未收到更新）自动向主程序发起同步请求"""
        last_request_t = 0
        
        while self._listener_running:
            now = time.time()
            has_data = False
            with self.df_lock:
                if self.current_df is not None and not self.current_df.empty:
                    has_data = True
            
            should_sync = False
            if not has_data:
                # 冷启动或无数据，且距离上次请求超过 15 秒
                if now - last_request_t > 15:
                    should_sync = True
            else:
                # 只有在有数据的情况下，若 10 分钟没有收到更新，且距离上次请求超过 60 秒
                if now - self.last_recv_t > 600:
                    if now - last_request_t > 60:
                        should_sync = True
            
            if should_sync:
                last_request_t = now
                self.request_full_sync()
            
            # 每隔 3 秒检查一次是否需要退出，避免 time.sleep(3) 引起的长退避
            for _ in range(3):
                if not self._listener_running:
                    break
                time.sleep(1)

    def _listen_loop(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.server_socket.bind(('127.0.0.1', self.port))
            self.server_socket.listen(5)
        except Exception as e:
            self.log_error(f"绑定端口 {self.port} 失败: {e}")
            return

        while self._listener_running:
            try:
                conn, addr = self.server_socket.accept()
                if not self._listener_running:
                    try: conn.close()
                    except: pass
                    break
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except Exception as e:
                if self._listener_running:
                    self.log_error(f"Socket accept 异常: {e}")
                break

    def _handle_client(self, conn):
        try:
            conn.settimeout(2.0)
            prefix = conn.recv(4)
            if not prefix or prefix != b"DATA":
                return
            
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
                    if cmd == 'UPDATE_DF_DATA':
                        self._process_data_package(body)
        except Exception as e:
            self.log_error(f"数据接收或解析异常: {e}")
        finally:
            try: conn.close()
            except: pass

    def _process_data_package(self, data_pkg):
        import pandas as pd
        self.last_recv_t = time.time()  # 记录最新一次行情接收的时间戳
        msg_type = 'UPDATE_DF_ALL'
        df_payload = None
        
        if isinstance(data_pkg, dict):
            msg_type = data_pkg.get('type', 'UPDATE_DF_ALL')
            df_payload = data_pkg.get('data')
            if df_payload is None:
                df_payload = data_pkg.get('full_snapshot')
        elif isinstance(data_pkg, pd.DataFrame):
            df_payload = data_pkg
        elif isinstance(data_pkg, tuple) and len(data_pkg) > 0:
            df_payload = data_pkg[0]
            
        if df_payload is None or not isinstance(df_payload, pd.DataFrame) or df_payload.empty:
            return

        # 1. 规整并对齐 DataFrame 索引 (规范为 6 位数字字符串)
        df_payload = df_payload.copy()
        if 'code' in df_payload.columns:
            df_payload['code'] = df_payload['code'].astype(str).str.strip().str.zfill(6)
            df_payload.set_index('code', inplace=True)
        else:
            df_payload.index = df_payload.index.astype(str).str.strip().str.zfill(6)
            df_payload.index.name = 'code'

        # 2. 合并更新 (全量/增量)
        with self.df_lock:
            if msg_type == 'UPDATE_DF_DIFF' and self.current_df is not None and not self.current_df.empty:
                try:
                    df_diff = df_payload
                    common_idx = self.current_df.index.intersection(df_diff.index)
                    if len(common_idx) > 0:
                        for col in df_diff.columns:
                            if col in self.current_df.columns:
                                try:
                                    col_data = df_diff.loc[common_idx, col]
                                    valid_mask = col_data.notna()
                                    valid_indices = valid_mask[valid_mask].index
                                    if len(valid_indices) > 0:
                                        self.current_df.loc[valid_indices, col] = df_diff.loc[valid_indices, col]
                                except Exception:
                                    pass
                    # 合并新增的个股
                    new_idx = df_diff.index.difference(self.current_df.index)
                    if len(new_idx) > 0:
                        self.current_df = pd.concat([self.current_df, df_diff.loc[new_idx]])
                except Exception as merge_err:
                    self.log_error(f"合并增量数据失败，降级为全量覆盖: {merge_err}")
                    self.current_df = df_payload
            else:
                self.current_df = df_payload

        # 3. 及时通知主进程确认已接收，防止主进程重试造成带宽挤占
        self._send_received_feedback()

        # 4. 触发外部 UI 渲染或业务处理回调
        if self.data_callback:
            try:
                self.data_callback(self.get_current_df())
            except Exception as cb_err:
                self.log_error(f"执行数据回调失败: {cb_err}")

    def _send_received_feedback(self):
        """通过管道发送确认指令"""
        cmd_dict = {"cmd": "ATS_RECEIVED"}
        payload = json.dumps(cmd_dict, ensure_ascii=False).encode("utf-8")
        try:
            import win32file
            handle = win32file.CreateFile(
                self.pipe_name, win32file.GENERIC_WRITE, 0, None,
                win32file.OPEN_EXISTING, 0, None
            )
            win32file.WriteFile(handle, payload)
            win32file.CloseHandle(handle)
        except Exception:
            pass
