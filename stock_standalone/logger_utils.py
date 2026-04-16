# -*- coding:utf-8 -*-
import sys
import functools
from JohnsonUtil import LoggerFactory

class SafeLoggerWriter:
    """防止管道关闭时抛出异常"""
    def __init__(self, log_func):
        self.log_func = log_func
        self.alive = True

    def write(self, message):
        if not self.alive:
            return
        msg = message.strip()
        if not msg:
            return
        try:
            self.log_func(msg)
        except Exception:
            self.alive = False
            sys.__stdout__.write(msg + "\n")

    def flush(self):
        try:
            sys.__stdout__.flush()
        except:
            pass

class LoggerWriter:
    """将 print 重定向到 logger，支持 end= 与防递归"""
    def __init__(self, log_func):
        self.log_func = log_func
        self._working = False
        self._buffer = ""

    def write(self, message):
        if not message:
            return
        if self._working:
            return
        try:
            self._working = True
            self._buffer += message
            while "\n" in self._buffer:
                line, self._buffer = self._buffer.split("\n", 1)
                line = line.strip()
                if line:
                    self.log_func(line)
        finally:
            self._working = False

    def flush(self):
        if self._buffer.strip():
            self.log_func(self._buffer.strip())
            self._buffer = ""

def init_logging(log_file="appTk.log", level=LoggerFactory.ERROR, redirect_print=False, show_detail=True):
    """初始化全局日志"""
    logger = LoggerFactory.getLogger(
        name="instock_TK",
        logpath=log_file,
        show_detail=show_detail
    )
    logger.setLevel(level)

    if redirect_print:
        sys.stdout = LoggerWriter(LoggerFactory.INFO)
        sys.stderr = LoggerWriter(LoggerFactory.ERROR)

    logger.info("日志初始化完成")
    return logger

def init_logging_noprint(log_file="appTk.log", level=LoggerFactory.ERROR, redirect_print=False, show_detail=True):
    """初始化全局日志 (简易版)"""
    logger = LoggerFactory.getLogger("instock_TK", logpath=log_file, show_detail=show_detail)
    logger.setLevel(level)

    if redirect_print:
        class SimpleLoggerWriter:
            def __init__(self, level_func):
                self.level_func = level_func
            def write(self, msg):
                msg = msg.strip()
                if msg:
                    self.level_func(msg)
            def flush(self):
                pass
        sys.stdout = SimpleLoggerWriter(level)
        sys.stderr = SimpleLoggerWriter(logger.error)

    logger.info("日志初始化完成")
    return logger

def with_log_level(level=LoggerFactory.INFO, logger_name=None):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            logger = LoggerFactory.getLogger(logger_name)
            old_level = logger.level
            try:
                logger.setLevel(level)
                return func(*args, **kwargs)
            finally:
                logger.setLevel(old_level)
        return wrapper
    return decorator