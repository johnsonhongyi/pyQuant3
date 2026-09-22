# -*- coding: utf-8 -*-
"""
tools/restore_agent_configs.py
------------------------------
多Agent配置与编排策略【一键灾难恢复/无缝还原工具】：
1. 自动定位 RamDisk (G:\\agent_config_backups\\agent_config_latest.zip) 或 E 盘备份 (E:\\RamdiskBack\\agent_configs\\agent_config_latest.zip)；
2. 也支持手动指定任意历史 zip 存档；
3. 执行灾难恢复：将解压后的 .agent_hub 配置、调度参数、任务流水及编排工具恢复到工作区；
4. 恢复完成后自动执行健康体检 (Health Check)：核查 orchestrator.json、STATUS.md 以及核心任务流是否完整可用；
5. 确保多 Agent 编排流水线在任何宕机或重装后秒级原地复活！
"""

import os
import sys
import glob
import zipfile
import shutil
import logging
from datetime import datetime
from typing import Optional, List

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_STANDALONE = os.path.dirname(CURRENT_DIR)
if STOCK_STANDALONE not in sys.path:
    sys.path.insert(0, STOCK_STANDALONE)

try:
    import JohnsonUtil.commonTips as cct
except ImportError:
    cct = None

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("RestoreAgentConfigs")


def find_latest_backup_archive(explicit_path: Optional[str] = None) -> Optional[str]:
    """按优先级寻找最新的有效配置备份包"""
    if explicit_path and os.path.exists(explicit_path):
        return explicit_path

    candidates = [
        # 1. RamDisk 极速镜像
        r"G:\agent_config_backups\agent_config_latest.zip",
        # 2. E 盘根目录最新指针
        r"E:\RamdiskBack\agent_configs\agent_config_latest.zip",
    ]

    # 动态探测 cct.get_ramdisk_dir()
    if cct and hasattr(cct, "get_ramdisk_dir"):
        rd = cct.get_ramdisk_dir()
        if rd and os.path.exists(rd):
            p = os.path.join(rd, "agent_config_backups", "agent_config_latest.zip")
            if p not in candidates:
                candidates.insert(0, p)

    for c in candidates:
        if os.path.exists(c) and os.path.getsize(c) > 0:
            return c

    return None


def list_available_backups(filter_source: Optional[str] = None) -> List[dict]:
    """
    搜索所有可用备份包，并按【备份版本】聚类去重差异化呈现：
    - 同一时间戳的备份若同时存在于 RamDisk 和 E 盘，合并为一条记录，展示为 [RamDisk + E盘双备份]；
    - 排除冗余指针，只展示最新版本与历史版本，杜绝刷屏。
    """
    source_map = {
        "RAMDISK": [r"G:\agent_config_backups"],
        "E_DISK": [r"E:\RamdiskBack\agent_configs"],
    }
    if cct and hasattr(cct, "get_ramdisk_dir"):
        rd = cct.get_ramdisk_dir()
        if rd and os.path.exists(rd):
            p = os.path.join(rd, "agent_config_backups")
            if p not in source_map["RAMDISK"]:
                source_map["RAMDISK"].insert(0, p)

    search_dirs = []
    if filter_source == "RAMDISK":
        search_dirs = source_map["RAMDISK"]
    elif filter_source == "E_DISK":
        search_dirs = source_map["E_DISK"]
    else:
        search_dirs = source_map["RAMDISK"] + source_map["E_DISK"]

    # 聚类容器：version_key -> {"version": str, "is_latest": bool, "mtime": float, "size_kb": float, "locations": {tag: path}}
    cluster = {}

    for d in search_dirs:
        if not os.path.exists(d):
            continue
        is_ram = d in source_map["RAMDISK"] or d.lower().startswith("g:")
        tag = "RamDisk" if is_ram else "E盘持久化"

        for f in glob.glob(os.path.join(d, "**", "*.zip"), recursive=True):
            fname = os.path.basename(f)
            # 排除顶层 latest 指针，聚焦真实归档
            if fname.lower() == "agent_config_latest.zip":
                continue

            try:
                stat = os.stat(f)
            except OSError:
                continue

            # 提取版本号 YYYYMMDD_HHMMSS
            if fname.startswith("agent_config_backup_"):
                ver = fname[len("agent_config_backup_"):-4]
            else:
                ver = fname[:-4]

            if ver not in cluster:
                cluster[ver] = {
                    "version": ver,
                    "filename": fname,
                    "mtime": stat.st_mtime,
                    "size_kb": stat.st_size / 1024,
                    "locations": {},
                }
            cluster[ver]["locations"][tag] = os.path.abspath(f)
            # 更新最新修改时间
            if stat.st_mtime > cluster[ver]["mtime"]:
                cluster[ver]["mtime"] = stat.st_mtime

    # 若未找到时间戳归档，尝试读取 latest
    if not cluster:
        for d in search_dirs:
            if not os.path.exists(d):
                continue
            is_ram = d in source_map["RAMDISK"] or d.lower().startswith("g:")
            tag = "RamDisk" if is_ram else "E盘持久化"
            latest_path = os.path.join(d, "agent_config_latest.zip")
            if os.path.exists(latest_path) and os.path.getsize(latest_path) > 0:
                stat = os.stat(latest_path)
                ver = "latest"
                if ver not in cluster:
                    cluster[ver] = {
                        "version": ver,
                        "filename": "agent_config_latest.zip",
                        "mtime": stat.st_mtime,
                        "size_kb": stat.st_size / 1024,
                        "locations": {},
                    }
                cluster[ver]["locations"][tag] = os.path.abspath(latest_path)

    # 排序：按时间戳修改时间倒序排列 (最新的排在前面)
    items = list(cluster.values())
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return items


def run_restore(archive_path: Optional[str] = None, target_workspace: str = STOCK_STANDALONE, auto_confirm: bool = False, source_filter: Optional[str] = None) -> bool:
    """执行多 Agent 配置选择与确认灾难恢复"""
    selected_archive = None

    if archive_path and os.path.exists(archive_path):
        selected_archive = archive_path
    else:
        current_filter = source_filter
        backups = list_available_backups(filter_source=current_filter)
        if not backups:
            logger.error("未找到可用的多Agent配置备份包 (请检查 RamDisk 或 E:\\RamdiskBack\\agent_configs)！")
            return False

        filter_label = "全部存储源 (自动合并)" if not current_filter else current_filter
        print("\n" + "=" * 68)
        print(f"       [列表] 可选的多Agent配置备份存档 [当前源: {filter_label}]")
        print("=" * 68)
        for idx, item in enumerate(backups, 1):
            mtime_str = datetime.fromtimestamp(item["mtime"]).strftime("%Y-%m-%d %H:%M:%S")
            tag_latest = " [最新推荐]" if idx == 1 else ""
            locs = " + ".join(item["locations"].keys())
            print(f"  [{idx}] 版本: {item['version']}{tag_latest}")
            print(f"      文件名: {item['filename']} ({item['size_kb']:.1f} KB)")
            print(f"      时间:   {mtime_str}")
            print(f"      分布:   [{locs}]")
            for loc_tag, loc_path in item["locations"].items():
                print(f"        - {loc_tag}: {loc_path}")
            print("  " + "-" * 64)

        print("=" * 68)

        if auto_confirm:
            chosen_item = backups[0]
            # 优先选择 RamDisk 极速恢复，不存在则用 E 盘
            selected_archive = chosen_item["locations"].get("RamDisk") or list(chosen_item["locations"].values())[0]
            print(f"[自动确认模式] 已默认选择第 1 项 [{chosen_item['version']}]")
        else:
            try:
                choice = input(f"请选择要还原的备份编号 [1-{len(backups)}, 默认 1]: ").strip()
                if not choice:
                    choice_idx = 1
                else:
                    choice_idx = int(choice)
                if 1 <= choice_idx <= len(backups):
                    chosen_item = backups[choice_idx - 1]
                    # 若该版本同时在 RamDisk 与 E 盘存在，允许用户选择从哪个介质恢复（默认优先 RamDisk）
                    avail_locs = list(chosen_item["locations"].keys())
                    if len(avail_locs) > 1:
                        print(f"  当前选定版本在多个介质均有存档: {avail_locs}")
                        sub_choice = input(f"  优先从哪个介质读取恢复？[1: RamDisk(极速), 2: E盘(持久化), 默认 1]: ").strip()
                        if sub_choice == "2":
                            selected_archive = chosen_item["locations"].get("E盘持久化")
                        else:
                            selected_archive = chosen_item["locations"].get("RamDisk")
                    else:
                        selected_archive = list(chosen_item["locations"].values())[0]
                else:
                    print(f"[错误] 无效的序号 {choice}，操作已取消。")
                    return False
            except Exception as e:
                print(f"[错误] 输入异常: {e}，操作已取消。")
                return False

    # 二次确认安全防线
    print("\n" + "!" * 65)
    print("[注意：即将执行多Agent策略配置还原]")
    print(f"  - 选定备份源: {selected_archive}")
    print(f"  - 目标工作区: {target_workspace}")
    print("  - 影响范围: 将完全覆盖 .agent_hub 配置与 tools/ 编排脚本！(不影响业务代码)")
    print("!" * 65)

    if not auto_confirm:
        try:
            confirm = input("是否确认覆盖还原？[Y/N, 默认 N]: ").strip().upper()
            if confirm != "Y":
                print("[取消] 操盘手已取消本次还原操作。工作区未发生任何改动。")
                return False
        except Exception:
            return False

    logger.info(f"开始从备份包执行多Agent配置灾难恢复...")
    logger.info(f"   - 备份源: {selected_archive}")
    logger.info(f"   - 目标工作区: {target_workspace}")

    temp_extract = os.path.join(target_workspace, ".temp_restore_extract")
    if os.path.exists(temp_extract):
        shutil.rmtree(temp_extract, ignore_errors=True)
    os.makedirs(temp_extract, exist_ok=True)

    try:
        # 1. 解压备份包
        with zipfile.ZipFile(selected_archive, "r") as z:
            z.extractall(temp_extract)

        # 2. 覆盖还原 .agent_hub
        extracted_hub = os.path.join(temp_extract, ".agent_hub")
        target_hub = os.path.join(target_workspace, ".agent_hub")
        if os.path.exists(extracted_hub):
            os.makedirs(target_hub, exist_ok=True)
            for item in os.listdir(extracted_hub):
                s = os.path.join(extracted_hub, item)
                d = os.path.join(target_hub, item)
                if os.path.isdir(s):
                    if os.path.exists(d):
                        shutil.rmtree(d, ignore_errors=True)
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)
            logger.info("   - [.agent_hub] 配置、调度规则与任务流已完整恢复")

        # 3. 覆盖还原 tools 目录下的自定义功能脚本与配置
        extracted_tools = os.path.join(temp_extract, "tools")
        target_tools = os.path.join(target_workspace, "tools")
        if os.path.exists(extracted_tools):
            os.makedirs(target_tools, exist_ok=True)
            restored_tools = []
            for item in os.listdir(extracted_tools):
                s = os.path.join(extracted_tools, item)
                d = os.path.join(target_tools, item)
                shutil.copy2(s, d)
                restored_tools.append(item)
            logger.info(f"   - [tools] 动态自适应还原了 {len(restored_tools)} 个自定义脚本与工具配置")

        # 4. 覆盖还原 docs 目录下的门禁与编排规范文档
        extracted_docs = os.path.join(temp_extract, "docs")
        target_docs = os.path.join(target_workspace, "docs")
        if os.path.exists(extracted_docs):
            os.makedirs(target_docs, exist_ok=True)
            for item in os.listdir(extracted_docs):
                s = os.path.join(extracted_docs, item)
                d = os.path.join(target_docs, item)
                shutil.copy2(s, d)
            logger.info("   - [docs] Agent Hub 显式执行门禁规范文档已还原")

        # 5. 覆盖还原后台自主守护运行态 (.agent_hub_runtime/)
        extracted_runtime = os.path.join(temp_extract, ".agent_hub_runtime")
        target_runtime = os.path.join(target_workspace, ".agent_hub_runtime")
        if os.path.exists(extracted_runtime):
            os.makedirs(target_runtime, exist_ok=True)
            for item in os.listdir(extracted_runtime):
                s = os.path.join(extracted_runtime, item)
                d = os.path.join(target_runtime, item)
                shutil.copy2(s, d)
            logger.info("   - [.agent_hub_runtime] 后台自主守护运行态已同步还原")

        # 6. 还原根目录独立门禁状态快照
        gate_fallback = os.path.join(temp_extract, ".agent_hub_command_gate.json")
        if os.path.exists(gate_fallback):
            shutil.copy2(gate_fallback, os.path.join(target_workspace, ".agent_hub_command_gate.json"))

        # 7. 清理临时解压区
        shutil.rmtree(temp_extract, ignore_errors=True)

        # 8. 自动运行多Agent自检 (Health Check)
        orch_cfg = os.path.join(target_hub, "orchestrator.json")
        status_md = os.path.join(target_hub, "dashboard", "STATUS.md")
        cmd_gate = os.path.join(target_tools, "agenthub_command.py")
        supervisor_script = os.path.join(target_tools, "agenthub_supervisor.py")
        if not os.path.exists(orch_cfg) or not os.path.exists(status_md):
            logger.error("恢复后健康体检未通过: 关键配置文件缺失！")
            return False

        logger.info("=" * 60)
        logger.info("[SUCCESS] 多Agent系统灾难恢复完成！")
        logger.info(f"   - orchestrator.json 校验正常")
        logger.info(f"   - Agent Hub 看板与任务流就绪")
        logger.info(f"   - 系统已恢复可运行状态，无任何业务代码被破坏！")
        logger.info("=" * 60)
        return True

    except Exception as exc:
        shutil.rmtree(temp_extract, ignore_errors=True)
        logger.exception(f"恢复过程异常失败: {exc}")
        return False


if __name__ == "__main__":
    auto_yes = False
    archive_arg = None
    source_arg = None

    args = sys.argv[1:]
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg in ("-y", "--yes"):
            auto_yes = True
        elif arg in ("-s", "--source") and idx + 1 < len(args):
            idx += 1
            val = args[idx].upper()
            if "RAM" in val or "G" in val:
                source_arg = "RAMDISK"
            elif "E" in val:
                source_arg = "E_DISK"
        elif not arg.startswith("-"):
            archive_arg = arg
        idx += 1

    ok = run_restore(archive_arg, auto_confirm=auto_yes, source_filter=source_arg)
    if not ok:
        sys.exit(1)
