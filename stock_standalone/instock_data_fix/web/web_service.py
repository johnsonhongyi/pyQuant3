#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import logging
import datetime
import json
import os
import os.path
import subprocess
import sys
import threading
import time
import uuid
import sqlite3
from abc import ABC
import tornado.escape
from tornado import gen
import tornado.httpserver
import tornado.ioloop
import tornado.options

# 在项目运行时，临时将项目路径添加到环境变量
cpath_current = os.path.dirname(os.path.dirname(__file__))
cpath = os.path.abspath(os.path.join(cpath_current, os.pardir))
sys.path.append(cpath)
log_path = os.path.join(cpath_current, 'log')
if not os.path.exists(log_path):
    os.makedirs(log_path)
logging.basicConfig(format='%(asctime)s %(message)s', filename=os.path.join(log_path, 'stock_web.log'))
logging.getLogger().setLevel(logging.ERROR)
import instock.lib.torndb as torndb
import instock.lib.database as mdb
import instock.lib.version as version
import instock.web.dataTableHandler as dataTableHandler
import instock.web.dataIndicatorsHandler as dataIndicatorsHandler
import instock.web.base as webBase
import instock.core.singleton_stock_web_module_data as sswmd
from instock.job.run_statistics import history, save, now
from instock.job.strategy_selection import selection, validate_selection
import instock.core.tablestructure as tbs

__author__ = 'myh '
__date__ = '2023/3/10 '


class Application(tornado.web.Application):
    def __init__(self):
        handlers = [
            # 设置路由
            (r"/", HomeHandler),
            (r"/instock/", HomeHandler),
            # 使用datatable 展示报表数据模块。
            (r"/instock/api_data", dataTableHandler.GetStockDataHandler),
            (r"/instock/data", dataTableHandler.GetStockHtmlHandler),
            # 获得股票指标数据。
            (r"/instock/data/indicators", dataIndicatorsHandler.GetDataIndicatorsHandler),
            (r"/instock/manual-strategy-refresh", ManualStrategyRefreshPageHandler),
            (r"/instock/api/manual-strategy-refresh", ManualStrategyRefreshHandler),
            (r"/instock/api/selected-strategies", SelectedStrategyRunHandler),
        ]
        settings = dict(  # 配置
            template_path=os.path.join(os.path.dirname(__file__), "templates"),
            static_path=os.path.join(os.path.dirname(__file__), "static"),
            xsrf_cookies=False,  # True,
            # cookie加密
            cookie_secret="027bb1b670eddf0392cdda8709268a17b58b7",
            debug=True,
        )
        super(Application, self).__init__(handlers, **settings)
        self.manual_strategy_refresh_lock = threading.Lock()
        self.manual_strategy_refresh_process = None
        self.manual_strategy_refresh_status = {
            "state": "idle", "started_at": None, "finished_at": None,
            "return_code": None, "pid": None
        }
        # Have one global connection to the blog DB across all handlers
        self.db = torndb.Connection(**mdb.MYSQL_CONN_TORNDB)


# 首页handler。
class HomeHandler(webBase.BaseHandler, ABC):
    @gen.coroutine
    def get(self):
        self.render("index.html",
                    stockVersion=version.__version__,
                    leftMenu=webBase.GetLeftMenu(self.request.uri))


class ManualStrategyRefreshPageHandler(webBase.BaseHandler, ABC):
    @gen.coroutine
    def get(self):
        menu_item = sswmd.stock_web_module_data().get_data("manual_strategy_refresh")
        self.render("manual_strategy_refresh.html",
                    web_module_data=menu_item,
                    stockVersion=version.__version__,
                    leftMenu=webBase.GetLeftMenu(self.request.uri))


class ManualStrategyRefreshHandler(webBase.BaseHandler, ABC):
    run_mode = 'small'
    def _wait_for_refresh(self, process, run_id, started):
        return_code = process.wait()
        state = 'success' if return_code == 0 else 'busy' if return_code == 75 else 'failed'
        record = save(run_id, getattr(self, 'run_mode', 'small'), state=state, finished_at=now(),
                      return_code=return_code,
                      duration_seconds=round(time.perf_counter() - started, 3))
        with self.application.manual_strategy_refresh_lock:
            if self.application.manual_strategy_refresh_process is process:
                self.application.manual_strategy_refresh_status = record

    def _status(self):
        with self.application.manual_strategy_refresh_lock:
            process = self.application.manual_strategy_refresh_process
            status = dict(self.application.manual_strategy_refresh_status)
            records = history()
            if status['state'] != 'running' and records[self.run_mode]:
                status = dict(records[self.run_mode][0])
            if status['state'] == 'running':
                started = status.get('started_at')
                if started:
                    status['duration_seconds'] = max(0, (datetime.datetime.now() -
                        datetime.datetime.strptime(started, '%Y-%m-%d %H:%M:%S')).total_seconds())
            status['history'] = records
            return status

    def get(self):
        self.set_header("Content-Type", "application/json;charset=UTF-8")
        self.write(json.dumps(self._status(), ensure_ascii=False))

    def post(self):
        self.set_header("Content-Type", "application/json;charset=UTF-8")
        names = None
        if self.run_mode == 'selected':
            try:
                body = json.loads(self.request.body)
                if not isinstance(body, dict) or body.get('action', 'run') not in ('run', 'save'):
                    raise ValueError('无效操作')
                names = ([] if body.get('action') == 'save' and body.get('strategies') == []
                         else validate_selection(body.get('strategies'), tbs.TABLE_CN_STOCK_STRATEGIES))
                if body.get('action') == 'save':
                    self.write({'saved': True, 'selected': selection(tbs.TABLE_CN_STOCK_STRATEGIES, names)})
                    return
            except (ValueError, OSError, sqlite3.Error) as exc:
                self.set_status(400 if isinstance(exc, ValueError) else 500)
                self.write({'state': 'failed', 'message': str(exc)})
                return
        with self.application.manual_strategy_refresh_lock:
            process = self.application.manual_strategy_refresh_process
            if process is not None and process.poll() is None:
                self.set_status(409)
                self.write(json.dumps({"state": "running", "message": "手动策略刷新正在运行"}, ensure_ascii=False))
                return

            env = os.environ.copy()
            env.pop('INSTOCK_SELECTED_STRATEGIES', None)
            env['INSTOCK_SMALL_STRATEGIES_ONLY'] = '1' if self.run_mode == 'small' else '0'
            if names is not None:
                try:
                    names = selection(tbs.TABLE_CN_STOCK_STRATEGIES, names)
                except (OSError, sqlite3.Error) as exc:
                    self.set_status(500)
                    self.write({'state': 'failed', 'message': str(exc)})
                    return
                env['INSTOCK_SELECTED_STRATEGIES'] = json.dumps(names)
            run_id = uuid.uuid4().hex
            env['INSTOCK_RUN_ID'] = run_id
            started = time.perf_counter()
            started_at = now()
            script_path = os.path.join(cpath_current, "job", "strategy_enter-edit.py")
            lock_path = os.path.join(cpath_current, "cache", "strategy_enter.lock")
            log_file = os.path.join(log_path, "manual_strategy_refresh.log")
            try:
                with open(log_file, "a", encoding="utf-8") as output:
                    process = subprocess.Popen(
                        ["/usr/bin/flock", "-n", "-E", "75", lock_path, sys.executable, script_path],
                        cwd=cpath,
                        env=env,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        close_fds=True
                    )
            except OSError as exc:
                self.set_status(500)
                self.write(json.dumps({"state": "failed", "message": str(exc)}, ensure_ascii=False))
                return

            status = {
                "state": "running", "started_at": started_at,
                "finished_at": None, "return_code": None, "pid": process.pid
            }
            status = save(run_id, self.run_mode, strategies=names, **status)
            self.application.manual_strategy_refresh_process = process
            self.application.manual_strategy_refresh_status = status
            threading.Thread(target=self._wait_for_refresh,
                             args=(process, run_id, started), daemon=True).start()
        self.set_status(202)
        self.write(json.dumps(status, ensure_ascii=False))


class SelectedStrategyRunHandler(ManualStrategyRefreshHandler):
    run_mode = 'selected'

    def get(self):
        self.set_header('Content-Type', 'application/json;charset=UTF-8')
        try:
            status = self._status()
            if status.get('mode') != 'selected' and status['state'] != 'running':
                status.update(state='idle', started_at=None, finished_at=None,
                              duration_seconds=0, return_code=None)
            status['options'] = [{'name': item['name'], 'label': item['cn']}
                                 for item in tbs.TABLE_CN_STOCK_STRATEGIES[2:]]
            status['selected'] = selection(tbs.TABLE_CN_STOCK_STRATEGIES)
            self.write(status)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self.set_status(500)
            self.write({'state': 'failed', 'message': str(exc)})


def main():
    # tornado.options.parse_command_line()
    tornado.options.options.logging = None

    http_server = tornado.httpserver.HTTPServer(Application())
    port = 9988
    http_server.listen(port)

    print(f"服务已启动，web地址 : http://localhost:{port}/")
    logging.error(f"服务已启动，web地址 : http://localhost:{port}/")

    tornado.ioloop.IOLoop.current().start()


if __name__ == "__main__":
    main()
