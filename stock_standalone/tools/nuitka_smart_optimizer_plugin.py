# -*- coding: utf-8 -*-
"""
Nuitka 智能编译加速与体积优化插件 (NuitkaSmartOptimizerPlugin)

核心机制：
1. 本地业务代码（stock_standalone 工程工作区内）：
   - 全量编译为 C 原生机器码（compiled），确保量化高频实时计算性能与核心策略算法的 100% 防反编译保护。
2. 第三方库（site-packages / Python 运行时扩展）：
   - 保留为 Python 字节码（bytecode），由内置解释器直接加载。
   - 彻底阻断对 NumPy/Pandas/PyQt6/openpyxl/aiohttp 等上千个三方模块的重复 C 转译，
     大幅削减 EXE 体积（预计减重 70~100MB），并将编译时间从 40 分钟降至数分钟。
"""

import os
from nuitka.plugins.PluginBase import NuitkaPluginBase
from nuitka.Tracing import plugins_logger


class NuitkaSmartOptimizerPlugin(NuitkaPluginBase):
    plugin_name = "smart-bytecode-optimizer"
    plugin_desc = "Optimize build size and compilation speed by keeping third-party packages as bytecode."

    def __init__(self):
        super().__init__()
        # 获取工程根目录物理绝对路径（统一规范为小写）
        self._project_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__))).lower()
        self._bytecode_modules = set()
        self._compiled_modules = set()
        self._logged_packages = set()

    def onModuleEncounter(self, using_module_name, module_name, module_filename, module_kind):
        if not module_filename:
            return None

        fn_lower = os.path.abspath(module_filename).lower()

        # 判定 1：位于 site-packages 或 Python 系统库的第三方依赖
        if "site-packages" in fn_lower or ("python" in fn_lower and "\\lib\\" in fn_lower):
            self._bytecode_modules.add(module_name)
            self.registerDecisionCompilation(module_name, "bytecode")
            top_pkg = module_name.asString().split(".")[0]
            if top_pkg not in self._logged_packages:
                self._logged_packages.add(top_pkg)
                plugins_logger.info(f"[SmartOptimizer] 第三方包保持为字节码 (跳过 C 编译): {top_pkg}")
            return None

        # 判定 2：属于工程源码工作区的核心业务代码
        if fn_lower.startswith(self._project_root):
            self._compiled_modules.add(module_name)
            self.registerDecisionCompilation(module_name, "compiled")
            return None

        return None

    def decideCompilation(self, module_name):
        if module_name in self._bytecode_modules:
            return "bytecode"
        if module_name in self._compiled_modules:
            return "compiled"

        # 兜底规则：知名第三方依赖库前缀全部设为 bytecode
        top_name = module_name.asString().split(".")[0].lower()
        known_thirdparty = {
            "pandas", "numpy", "openpyxl", "pyqtgraph", "aiohttp", "requests", "urllib3",
            "tushare", "pytdx", "chardet", "tables", "pyqt6", "tzdata", "dateutil",
            "yaml", "websocket", "tqdm", "bs4", "win32com", "pywin", "psutil",
            "simplejson", "charset_normalizer", "yarl", "propcache", "multidict",
            "frozenlist", "attr", "certifi", "idna", "six", "wrapt", "packaging",
            "zstandard", "numexpr", "cffi", "et_xmlfile", "soupsieve", "aiohappyeyeballs"
        }
        if top_name in known_thirdparty:
            return "bytecode"

        return None
