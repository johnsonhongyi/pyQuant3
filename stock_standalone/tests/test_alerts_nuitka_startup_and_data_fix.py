# -*- coding: utf-8 -*-
import os
import sys
import pytest

# 添加路径
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(current_dir)
tdxgui_dir = os.path.join(repo_root, "..", "stock", "testpy", "tdxgui")
webtools_dir = os.path.join(repo_root, "..", "stock", "webTools")

sys.path.insert(0, os.path.abspath(tdxgui_dir))

def test_sys_utils_resource_map_includes_linkage():
    import sys_utils
    assert "linkage_config.json" in sys_utils.RESOURCE_MAP
    assert sys_utils.RESOURCE_MAP["linkage_config.json"]["src"] == "linkage_config.json"
    p = sys_utils.get_conf_path("linkage_config.json")
    assert p.endswith("linkage_config.json")

def test_build_bat_tables_and_dll_inclusion():
    bat_path = os.path.join(tdxgui_dir, "build_nuitka_clang.bat")
    with open(bat_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "--nofollow-import-to=tables" not in content, "tables must NOT be blocked"
    assert "--include-package=tables" in content
    assert "--include-module=tables._comp_lzo" in content
    assert "--include-module=filelock" in content
    assert "CRYPTO_DLL" in content
    assert "SSL_DLL" in content
    assert "--include-data-file=linkage_config.json=linkage_config.json" in content

def test_yidong_liandong_config_and_geometry():
    yd_path = os.path.join(tdxgui_dir, "异动联动.py")
    with open(yd_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 验证 linkage_config.json 使用了 get_conf_path
    assert 'get_conf_path("linkage_config.json", BASE_DIR' in content

    # 验证 root 主窗口位置恢复与保存
    assert 'WINDOW_GEOMETRIES.get("root")' in content
    assert 'root.bind("<Configure>", _on_root_configure_save' in content

    # 验证 dff 计算的有效性过滤
    assert 'invalid_mask = (pd.to_numeric(top_all[\'buy\'], errors=\'coerce\').fillna(0) <= 0)' in content

def test_ths_tdx_web_and_find_set_window_pos():
    ths_web_path = os.path.join(webtools_dir, "ths-tdx-web.py")
    with open(ths_web_path, "r", encoding="utf-8") as f:
        ths_content = f.read()
    assert "异动联动_Nuitka.exe" in ths_content

    fsw_path = os.path.join(webtools_dir, "findSetWindowPos.py")
    with open(fsw_path, "r", encoding="utf-8") as f:
        fsw_content = f.read()
    assert "positon[proc] = '0,0,494,825'" in fsw_content
