# -*- coding: utf-8 -*-
import os
import sys
import tempfile
import pytest

# 将项目根目录和 webTools 动态加入 sys.path，支持单脚本直接运行
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
webtools_dir = os.path.join(parent_dir, "webTools")
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)
if webtools_dir not in sys.path:
    sys.path.insert(0, webtools_dir)

import sys_utils
from sys_utils import get_app_root, is_packaged_env
from webTools.window_manager import core, ConfigManager


@pytest.fixture(autouse=True)
def reset_app_root_cache():
    """每个测试前后重置内存缓存，确保环境模拟隔离"""
    sys_utils._CACHED_APP_ROOT = None
    yield
    sys_utils._CACHED_APP_ROOT = None


def test_dev_mode_app_root():
    """源码开发模式下正常获取开发目录"""
    root = get_app_root()
    assert os.path.exists(root)
    assert os.path.isabs(root)


def test_frozen_mode_ignores_external_env_root():
    """PyInstaller / Nuitka 打包模式下，即使外界存在污染的环境变量，也必须 100% 锁定真实物理 EXE 目录"""
    orig_env = os.environ.get("INSTOCK_APP_ROOT")
    orig_frozen = getattr(sys, "frozen", False)
    orig_exe = sys.executable
    orig_argv = list(sys.argv)

    try:
        os.environ["INSTOCK_APP_ROOT"] = r"C:\Wrong\Polluted\Path"
        sys.frozen = True
        fake_exe = r"C:\Users\Johnson\Documents\TDX\55188\manage_window_layout.exe"
        sys.executable = fake_exe
        sys.argv = [fake_exe]

        # sys_utils.get_app_root
        resolved_root = get_app_root()
        assert resolved_root == r"C:\Users\Johnson\Documents\TDX\55188"
        assert os.environ["INSTOCK_APP_ROOT"] == r"C:\Users\Johnson\Documents\TDX\55188"

        # core.get_app_root
        core_root = core.get_app_root()
        assert core_root == r"C:\Users\Johnson\Documents\TDX\55188"

    finally:
        sys.frozen = orig_frozen
        sys.executable = orig_exe
        sys.argv = orig_argv
        if orig_env is not None:
            os.environ["INSTOCK_APP_ROOT"] = orig_env
        else:
            os.environ.pop("INSTOCK_APP_ROOT", None)


def test_nuitka_worker_child_process_inherits_main_app_root():
    """Nuitka Onefile 解压到临时目录的 worker 子进程，正确继承主进程传递的非临时物理根目录"""
    orig_env = os.environ.get("INSTOCK_APP_ROOT")
    orig_frozen = getattr(sys, "frozen", False)
    orig_exe = sys.executable
    orig_argv = list(sys.argv)
    orig_nuitka = os.environ.get("NUITKA_ONEFILE_DIRECTORY")

    try:
        sys.frozen = False
        os.environ["NUITKA_ONEFILE_DIRECTORY"] = r"C:\Users\Johnson\AppData\Local\Temp\onefile_99999"
        os.environ["INSTOCK_APP_ROOT"] = r"C:\Users\Johnson\Documents\TDX\55188"
        sys.executable = r"C:\Users\Johnson\AppData\Local\Temp\onefile_99999\child.exe"
        sys.argv = [r"C:\Users\Johnson\AppData\Local\Temp\onefile_99999\child.exe"]

        resolved = get_app_root()
        assert resolved == r"C:\Users\Johnson\Documents\TDX\55188"
    finally:
        sys.frozen = orig_frozen
        sys.executable = orig_exe
        sys.argv = orig_argv
        if orig_env is not None:
            os.environ["INSTOCK_APP_ROOT"] = orig_env
        else:
            os.environ.pop("INSTOCK_APP_ROOT", None)
        if orig_nuitka is not None:
            os.environ["NUITKA_ONEFILE_DIRECTORY"] = orig_nuitka
        else:
            os.environ.pop("NUITKA_ONEFILE_DIRECTORY", None)


def test_get_conf_path_single_source_of_truth():
    """当运行目录下已有配置文件时，永远直接返回该文件，绝不发生回退"""
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_cfg = os.path.join(tmpdir, "window_layout_config.json")
        with open(fake_cfg, "w", encoding="utf-8") as f:
            f.write('{"single_display": {}, "multi_display": {"custom_test": {"app": "1,2,3,4"}}, "custom_special": {}}')

        # 模拟 app_root 位于 tmpdir
        orig_env = os.environ.get("INSTOCK_APP_ROOT")
        try:
            os.environ["INSTOCK_APP_ROOT"] = tmpdir
            conf_path = core.get_conf_path("window_layout_config.json")
            assert os.path.normpath(conf_path) == os.path.normpath(fake_cfg)

            mgr = ConfigManager(conf_path)
            assert "custom_test" in mgr.get_resolutions_by_category("multi_display")
            assert mgr.get_resolution_mapping("custom_test") == {"app": "1,2,3,4"}
        finally:
            if orig_env is not None:
                os.environ["INSTOCK_APP_ROOT"] = orig_env
            else:
                os.environ.pop("INSTOCK_APP_ROOT", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
