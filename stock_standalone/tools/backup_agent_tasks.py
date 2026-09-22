# -*- coding: utf-8 -*-
"""
tools/backup_agent_tasks.py
---------------------------
专注【多Agent配置与任务体系】自动化备份打包工具：
1. 纯粹性：严格只打包多Agent配置、编排规则、任务模板、状态看板与决策记录，坚决不夹杂业务代码！
2. 双轨备份：自动识别 RamDisk 目录 (G:\\agent_config_backups) 与 E 盘备份路径 (E:\\RamdiskBack\\agent_configs)；
3. 按日期打包：生成格式为 agent_config_backup_YYYYMMDD_HHMMSS.zip；
4. 便捷指针：同时生成根目录与子目录下的 agent_config_latest.zip；
5. 生命周期淘汰：严格保留最近 5 个存档，自动删除过期旧包；
6. 配套还原脚本：提供一键将多Agent配置还原/部署回当前工作区的极简脚本。
"""

import os
import sys
import glob
import shutil
import logging
from datetime import datetime
from typing import List, Optional, Tuple

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
logger = logging.getLogger("BackupAgentConfigs")

MAX_KEEP_ARCHIVES = 5
DEFAULT_E_BACKUP_ROOT = r"E:\RamdiskBack\agent_configs"
ZIP_PREFIX = "agent_config_backup_"
LATEST_ZIP_NAME = "agent_config_latest.zip"


def resolve_ramdisk_backup_root() -> Optional[str]:
    """解析并确保 RamDisk 下的 agent 配置备份目录"""
    ram_dir = None
    if cct and hasattr(cct, "get_ramdisk_dir"):
        ram_dir = cct.get_ramdisk_dir()
    if not ram_dir or not os.path.exists(ram_dir):
        for candidate in ("G:\\", "G:", "R:\\", "R:"):
            if os.path.exists(candidate):
                ram_dir = candidate if candidate.endswith(os.sep) else candidate + os.sep
                break

    if ram_dir and os.path.exists(ram_dir):
        if os.name == 'nt' and len(ram_dir) == 2 and ram_dir[1] == ':':
            ram_dir += os.sep
        target = os.path.join(ram_dir, "agent_config_backups")
        os.makedirs(target, exist_ok=True)
        return target
    return None


def resolve_e_backup_root() -> str:
    """解析并确保 E 盘持久化备份目录"""
    e_root = DEFAULT_E_BACKUP_ROOT
    if not os.path.exists("E:\\"):
        e_root = os.path.join(STOCK_STANDALONE, "backup_store", "agent_configs")
    os.makedirs(e_root, exist_ok=True)
    return e_root


def collect_agent_configs(staging_dir: str) -> None:
    """
    纯粹收集【多Agent配置与任务体系】：
    - .agent_hub/orchestrator.json (核心调度配置)
    - .agent_hub/PROMPT_PROTOCOL.md (提示词与交互协议)
    - .agent_hub/review_prompt.md (审核人提示词)
    - .agent_hub/task_template.md (任务模板)
    - .agent_hub/master_plan.md (总规划)
    - .agent_hub/dashboard/ (当前状态与状态看板)
    - .agent_hub/decisions/ (决策与合并报告)
    - .agent_hub/events/ (事件流 events.jsonl)
    - .agent_hub/inbox/, .agent_hub/done/, .agent_hub/running/, .agent_hub/review/ (全量任务书)
    - tools/agent_orchestrator.py, tools/agent_hub.py (编排器执行脚本)
    - 严格排除：业务代码 (ats/*, trading_kernel/*, tests/* 等)
    """
    logger.info(f"正在纯粹收集多Agent配置与编排规则至暂存区: {staging_dir}")
    if os.path.exists(staging_dir):
        shutil.rmtree(staging_dir, ignore_errors=True)
    os.makedirs(staging_dir, exist_ok=True)

    # 1. 复制 .agent_hub 全部配置与任务文件 (排除锁和个人临时目录)
    agent_hub_src = os.path.join(STOCK_STANDALONE, ".agent_hub")
    agent_hub_dst = os.path.join(staging_dir, ".agent_hub")
    if os.path.exists(agent_hub_src):
        def _ignore_locks_and_temps(folder, files):
            ignored = []
            for f in files:
                if f.endswith('.lock') or f.endswith('.tmp') or f == '__pycache__' or f == '.worker_profile':
                    ignored.append(f)
                # 排除可能包含超大生成的临时产物
                elif f == "artifacts" and folder == agent_hub_src:
                    pass
            return ignored
        shutil.copytree(agent_hub_src, agent_hub_dst, ignore=_ignore_locks_and_temps)

    # 2. 复制编排执行脚本 (只收敛 agent 调度器本身)
    tools_dst = os.path.join(staging_dir, "tools")
    os.makedirs(tools_dst, exist_ok=True)
    orchestrator_scripts = ["agent_orchestrator.py", "agent_hub.py", "backup_agent_tasks.py"]
    for s_name in orchestrator_scripts:
        s_path = os.path.join(STOCK_STANDALONE, "tools", s_name)
        if os.path.exists(s_path):
            shutil.copy2(s_path, tools_dst)

    # 3. 复制工作区根目录下与多任务编排相关的专用规范
    root_agent_files = [
        "20260920_2228_task.md",
    ]
    for rf in root_agent_files:
        src_f = os.path.join(STOCK_STANDALONE, rf)
        if os.path.exists(src_f):
            shutil.copy2(src_f, staging_dir)

    # 4. 生成一键还原多Agent配置脚本 (Restore Script)
    restore_bat = os.path.join(staging_dir, "一键还原多Agent配置.bat")
    with open(restore_bat, "w", encoding="gbk", errors="ignore") as f:
        f.write('''@echo off
chcp 936 >nul
echo 正在将备份的多Agent配置与编排规则还原至工作区...
set "TARGET_WS=D:\\MacTools\\WorkFile\\WorkSpace\\pyQuant3\\stock_standalone"

xcopy /E /Y /I "%~dp0.agent_hub" "%TARGET_WS%\\.agent_hub"
xcopy /Y "%~dp0tools\\*.*" "%TARGET_WS%\\tools\\"

echo 多Agent配置还原完毕！
pause
''')


def prune_old_archives(archive_dir: str, max_keep: int = MAX_KEEP_ARCHIVES) -> List[str]:
    """严格保留最近的 max_keep 个压缩包，自动删除过期旧包"""
    pattern = os.path.join(archive_dir, f"{ZIP_PREFIX}*.zip")
    zips = glob.glob(pattern)
    # 按文件修改时间升序排列 (最旧的在前面)
    zips.sort(key=lambda x: os.path.getmtime(x))

    deleted = []
    if len(zips) > max_keep:
        to_delete = zips[:len(zips) - max_keep]
        for fpath in to_delete:
            try:
                os.remove(fpath)
                deleted.append(os.path.basename(fpath))
                logger.info(f"已轮转清理多余旧配置包: {os.path.basename(fpath)}")
            except Exception as ex:
                logger.warning(f"清理旧包失败 {fpath}: {ex}")
    return deleted


def create_backup_archive(staging_dir: str, target_root: str, max_keep: int = MAX_KEEP_ARCHIVES, timestamp: Optional[datetime] = None) -> Tuple[str, str]:
    """生成带时间戳归档与 latest 归档，并执行生命周期轮转清理"""
    now = timestamp or datetime.now()
    today_str = now.strftime("%Y%m%d")
    time_str = now.strftime("%Y%m%d_%H%M%S")

    # 1. 在带日期的子目录下存放
    date_sub_dir = os.path.join(target_root, today_str)
    os.makedirs(date_sub_dir, exist_ok=True)

    archive_base = os.path.join(date_sub_dir, f"{ZIP_PREFIX}{time_str}")
    zip_path = shutil.make_archive(archive_base, "zip", staging_dir)

    # 2. 生成 latest 便捷指针 (顶层根目录与子目录)
    latest_sub = os.path.join(date_sub_dir, LATEST_ZIP_NAME)
    shutil.copy2(zip_path, latest_sub)

    latest_root = os.path.join(target_root, LATEST_ZIP_NAME)
    shutil.copy2(zip_path, latest_root)

    # 3. 自动在日期子目录保留最近 5 个时间戳归档
    prune_old_archives(date_sub_dir, max_keep=max_keep)

    return zip_path, latest_root


def run_backup(max_keep: int = MAX_KEEP_ARCHIVES) -> dict:
    """运行全流程：暂存 -> 纯配置打包 -> RamDisk 与 E: 双轨备份 -> 滚动清理保留最近 5 个"""
    start_time = datetime.now()
    ram_root = resolve_ramdisk_backup_root()
    e_root = resolve_e_backup_root()

    # 使用临时暂存目录
    temp_staging = os.path.join(STOCK_STANDALONE, ".temp_agent_config_staging")
    summary = {
        "status": "INIT",
        "scope": "Agent Configs & Orchestration Rules Only (Zero Business Code)",
        "ramdisk_dir": ram_root,
        "e_backup_dir": e_root,
        "e_archive_path": None,
        "latest_pointer": None,
        "size_kb": 0.0,
        "max_keep": max_keep,
        "timestamp": start_time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    try:
        # 1. 收集纯配置
        collect_agent_configs(temp_staging)

        # 2. 备份至 E: 盘
        e_zip, latest_ptr = create_backup_archive(temp_staging, e_root, max_keep=max_keep, timestamp=start_time)
        summary["e_archive_path"] = e_zip
        summary["latest_pointer"] = latest_ptr
        summary["size_kb"] = round(os.path.getsize(e_zip) / 1024.0, 1)

        # 3. 若 RamDisk 存在，同样备份至 RamDisk (版本时间戳保持 100% 同步)
        if ram_root:
            ram_zip, _ = create_backup_archive(temp_staging, ram_root, max_keep=max_keep, timestamp=start_time)
            summary["ramdisk_archive_path"] = ram_zip

        # 清理临时暂存目录
        shutil.rmtree(temp_staging, ignore_errors=True)

        summary["status"] = "SUCCESS"
        logger.info("=" * 60)
        logger.info(f"✅ [SUCCESS] 多Agent配置专属备份完成！")
        logger.info(f"   • 包含范围: 纯Agent配置/编排/任务/状态看板 (无业务代码)")
        logger.info(f"   • 压缩包大小: {summary['size_kb']} KB")
        logger.info(f"   • E盘主存储: {summary['e_archive_path']}")
        logger.info(f"   • 最新便捷指针: {summary['latest_pointer']}")
        if ram_root:
            logger.info(f"   • RamDisk极速备份: {summary.get('ramdisk_archive_path')}")
        logger.info(f"   • 保留策略: 严格仅保留最近 {max_keep} 个存档")
        logger.info("=" * 60)
        return summary

    except Exception as exc:
        shutil.rmtree(temp_staging, ignore_errors=True)
        summary["status"] = "FAILED"
        summary["error"] = str(exc)
        logger.exception(f"❌ 备份异常: {exc}")
        return summary


if __name__ == "__main__":
    result = run_backup(max_keep=MAX_KEEP_ARCHIVES)
    print(f"\n[Done] Status: {result['status']}, Size: {result.get('size_kb')} KB")
    if result["status"] != "SUCCESS":
        sys.exit(1)
