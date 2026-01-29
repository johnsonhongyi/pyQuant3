# -*- coding: utf-8 -*-
"""
概念分析查看器 IPC 管理器

用于 TK 主程序与独立 Qt 概念查看器进程之间的通信
"""

import os
import sys
import json
import socket
import struct
import subprocess
import threading
import time
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime
import logging

logger = logging.getLogger("instock_TK.ConceptIPC")

# IPC 端口配置
IPC_SEND_PORT = 26670      # 发送数据到查看器
IPC_CALLBACK_PORT = 26671  # 接收查看器回调


class ConceptViewerManager:
    """
    概念分析查看器进程管理器
    
    功能：
    - 启动/管理独立的 Qt 查看器进程
    - 通过 Socket 发送数据更新
    - 接收查看器的交互回调
    """
    
    def __init__(self, callback_handler: Optional[Callable[[Dict], None]] = None):
        """
        初始化管理器
        
        Args:
            callback_handler: 处理查看器回调的函数
        """
        self._processes: Dict[str, subprocess.Popen] = {}  # unique_code -> process
        self._callback_handler = callback_handler
        self._callback_server = None
        self._callback_thread = None
        self._running = True
        
        # 启动回调监听
        self._start_callback_listener()
    
    def _start_callback_listener(self):
        """启动回调监听服务"""
        self._callback_thread = threading.Thread(
            target=self._callback_listen_loop, 
            daemon=True,
            name="ConceptViewerCallback"
        )
        self._callback_thread.start()
    
    def _callback_listen_loop(self):
        """回调监听循环"""
        try:
            self._callback_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._callback_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._callback_server.bind(('127.0.0.1', IPC_CALLBACK_PORT))
            self._callback_server.listen(10)
            self._callback_server.settimeout(1.0)
            
            logger.info(f"[ConceptIPC] 回调监听启动: 127.0.0.1:{IPC_CALLBACK_PORT}")
            
            while self._running:
                try:
                    conn, addr = self._callback_server.accept()
                    # 在新线程中处理，避免阻塞
                    threading.Thread(
                        target=self._handle_callback, 
                        args=(conn,),
                        daemon=True
                    ).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self._running:
                        logger.warning(f"[ConceptIPC] 回调接收错误: {e}")
        except OSError as e:
            if "10048" in str(e) or "Address already in use" in str(e):
                logger.warning(f"[ConceptIPC] 回调端口 {IPC_CALLBACK_PORT} 已被占用，可能另一实例正在运行")
            else:
                logger.error(f"[ConceptIPC] 回调监听启动失败: {e}")
        except Exception as e:
            logger.error(f"[ConceptIPC] 回调监听启动失败: {e}")
    
    def _handle_callback(self, conn):
        """处理单个回调连接"""
        try:
            # 读取消息长度
            length_data = conn.recv(4)
            if len(length_data) < 4:
                return
            
            msg_length = struct.unpack('>I', length_data)[0]
            
            # 读取消息体
            msg_data = b''
            while len(msg_data) < msg_length:
                chunk = conn.recv(min(4096, msg_length - len(msg_data)))
                if not chunk:
                    break
                msg_data += chunk
            
            data = json.loads(msg_data.decode('utf-8'))
            cmd = data.get('cmd', '')
            unique_code = data.get('unique_code', '')
            
            logger.info(f"[ConceptIPC] 收到回调: cmd={cmd}, unique_code={unique_code}")
            
            # 处理特殊命令
            if cmd == 'VIEWER_CLOSED':
                # 查看器已关闭，清理进程记录
                if unique_code in self._processes:
                    del self._processes[unique_code]
                    logger.info(f"[ConceptIPC] 查看器已关闭: {unique_code}")
            
            # 调用用户回调
            if self._callback_handler:
                try:
                    self._callback_handler(data)
                except Exception as e:
                    logger.error(f"[ConceptIPC] 回调处理器错误: {e}")
            
        except Exception as e:
            logger.warning(f"[ConceptIPC] 处理回调失败: {e}")
        finally:
            try:
                conn.close()
            except:
                pass
    
    def launch_viewer(self, code: str, top_n: int, initial_data: Optional[Dict] = None) -> bool:
        """
        启动或聚焦概念分析查看器
        
        Args:
            code: 股票代码或 "总览"
            top_n: 显示前 N 个概念
            initial_data: 初始数据 (可选)
        
        Returns:
            是否成功启动
        """
        unique_code = f"{code}_{top_n}"
        
        # 检查是否已有进程
        if unique_code in self._processes:
            proc = self._processes[unique_code]
            if proc.poll() is None:
                # 进程仍在运行，发送聚焦命令
                logger.info(f"[ConceptIPC] 查看器已存在，发送聚焦: {unique_code}")
                self._send_to_viewer({'cmd': 'FOCUS'})
                return True
            else:
                # 进程已退出，清理
                del self._processes[unique_code]
        
        try:
            # 构建启动命令
            viewer_path = self._get_viewer_path()
            if not viewer_path:
                logger.error("[ConceptIPC] 找不到 concept_viewer.py")
                return False
            
            cmd = [
                sys.executable,
                viewer_path,
                '--code', str(code),
                '--top_n', str(top_n)
            ]
            
            # 如果有初始数据，通过参数传递
            if initial_data:
                cmd.extend(['--data', json.dumps(initial_data, ensure_ascii=False)])
            
            # 启动子进程
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0
            )
            
            self._processes[unique_code] = proc
            logger.info(f"[ConceptIPC] 启动查看器: {unique_code}, PID={proc.pid}")
            
            return True
            
        except Exception as e:
            logger.error(f"[ConceptIPC] 启动查看器失败: {e}")
            return False
    
    def update_viewer(self, code: str, top_n: int, data: Dict) -> bool:
        """
        发送数据更新到查看器
        
        Args:
            code: 股票代码
            top_n: 显示数量
            data: 更新数据 (concepts, scores, avg_percents, follow_ratios)
        
        Returns:
            是否发送成功
        """
        unique_code = f"{code}_{top_n}"
        
        # 检查进程是否还活着
        if unique_code not in self._processes:
            return False
        
        proc = self._processes[unique_code]
        if proc.poll() is not None:
            # 进程已退出
            del self._processes[unique_code]
            return False
        
        # 构造更新消息
        msg_data = {
            'cmd': 'UPDATE_DATA',
            'code': code,
            'top_n': top_n,
            **data
        }
        
        return self._send_to_viewer(msg_data)
    
    def _send_to_viewer(self, data: Dict) -> bool:
        """发送消息到查看器"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect(('127.0.0.1', IPC_SEND_PORT))
            
            msg = json.dumps(data, ensure_ascii=False).encode('utf-8')
            sock.send(struct.pack('>I', len(msg)) + msg)
            sock.close()
            return True
        except Exception as e:
            logger.warning(f"[ConceptIPC] 发送到查看器失败: {e}")
            return False
    
    def close_viewer(self, code: str, top_n: int):
        """关闭指定的查看器"""
        unique_code = f"{code}_{top_n}"
        
        if unique_code in self._processes:
            proc = self._processes[unique_code]
            if proc.poll() is None:
                # 发送关闭命令
                self._send_to_viewer({'cmd': 'CLOSE'})
                
                # 等待进程退出
                try:
                    proc.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
            
            del self._processes[unique_code]
    
    def close_all(self):
        """关闭所有查看器"""
        for unique_code in list(self._processes.keys()):
            code, top_n = unique_code.rsplit('_', 1)
            self.close_viewer(code, int(top_n))
    
    def is_viewer_running(self, code: str, top_n: int) -> bool:
        """检查查看器是否正在运行"""
        unique_code = f"{code}_{top_n}"
        if unique_code not in self._processes:
            return False
        
        proc = self._processes[unique_code]
        if proc.poll() is not None:
            del self._processes[unique_code]
            return False
        
        return True
    
    def shutdown(self):
        """关闭管理器"""
        self._running = False
        self.close_all()
        
        if self._callback_server:
            try:
                self._callback_server.close()
            except:
                pass
    
    def _get_viewer_path(self) -> Optional[str]:
        """获取 concept_viewer.py 的路径"""
        if getattr(sys, 'frozen', False):
            # 打包环境
            base_path = os.path.dirname(sys.executable)
            exe_path = os.path.join(base_path, 'concept_viewer.exe')
            if os.path.exists(exe_path):
                return exe_path
        
        # 开发环境
        base_path = os.path.dirname(os.path.abspath(__file__))
        py_path = os.path.join(base_path, 'concept_viewer.py')
        if os.path.exists(py_path):
            return py_path
        
        return None
