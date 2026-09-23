# -*- coding: utf-8 -*-
"""
tools/archive_build_exe.py
打包产物自动归档与生命周期清理工具

职责：
1. 打包前检查目标路径（如 dist/ATS_Terminal.exe）是否存在旧文件，
   若存在则自动归档至 dist/archive/ 目录下，并以旧文件实际构建时间戳命名，
   彻底防止新版本覆盖旧版本导致出现 Bug 时无法回退与对比排错。
2. 自动清理归档目录中超过指定天数（默认 7 天）的历史打包版本，
   始终只保留最近 7 天的打包历史，节约磁盘空间。
3. 打包后（post-build）自动为新打包生成的 exe 建立快照归档并列出当前历史版本清单。
4. 纯标准库实现，零第三方依赖，异常全面捕获，绝对不中断 PyInstaller 主构建流程。
"""

import os
import sys
import shutil
import argparse
import datetime
import re
from pathlib import Path
from typing import List, Tuple, Optional

# 跨环境与管道重定向 UTF-8 中文输出适配
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def resolve_target_from_spec(spec_path: Path, dist_dir: Optional[Path] = None) -> Path:
    """
    自适应从 .spec 配置文件中解析出目标构建产物 exe 路径。
    1. 读取 spec 文件内容，通过正则提取 EXE(...) 中的 name='...' 属性；
    2. 若未显式定义 name，则回退使用 spec 文件名主干（stem）；
    3. 拼接输出目录（默认为 spec 同级或当前目录下的 dist 目录）。
    """
    spec_path = spec_path.resolve()
    base_dir = spec_path.parent
    if dist_dir is None:
        dist_dir = base_dir / "dist"

    exe_stem = spec_path.stem
    if spec_path.exists() and spec_path.is_file():
        try:
            content = spec_path.read_text(encoding="utf-8", errors="ignore")
            # 优先匹配 EXE(..., name='...', ...)
            m = re.search(r"EXE\s*\([^)]*name\s*=\s*['\"]([^'\"]+)['\"]", content, re.DOTALL)
            if not m:
                # 宽松匹配任意 name='xxx' 赋值
                m = re.search(r"name\s*=\s*['\"]([^'\"]+)['\"]", content)
            if m:
                exe_stem = m.group(1).strip()
        except Exception as e:
            print(f"[警告] 解析 spec 配置文件失败 ({spec_path.name}): {e}，回退使用 spec 文件名主干")

    # 规范化后缀为 .exe
    if not exe_stem.lower().endswith(".exe"):
        exe_filename = f"{exe_stem}.exe"
    else:
        exe_filename = exe_stem

    return dist_dir / exe_filename


def parse_timestamp_from_filename(filename: str) -> Optional[datetime.datetime]:
    """
    尝试从文件名中提取 YYYYMMDD_HHMMSS 或 YYYYMMDD 时间戳
    例如: ATS_Terminal_20260923_115523.exe -> 2026-09-23 11:55:23
    """
    # 匹配 _YYYYMMDD_HHMMSS
    m = re.search(r'_(\d{8})_(\d{6})', filename)
    if m:
        try:
            return datetime.datetime.strptime(f"{m.group(1)}_{m.group(2)}", "%Y%m%d_%H%M%S")
        except ValueError:
            pass

    # 匹配 _YYYYMMDD
    m2 = re.search(r'_(\d{8})', filename)
    if m2:
        try:
            return datetime.datetime.strptime(m2.group(1), "%Y%m%d")
        except ValueError:
            pass

    return None


def get_file_datetime(filepath: Path) -> datetime.datetime:
    """
    获取文件的基准时间：优先文件名时间戳，若无则使用文件系统最后修改时间 mtime
    """
    dt_from_name = parse_timestamp_from_filename(filepath.name)
    if dt_from_name is not None:
        return dt_from_name

    try:
        mtime = os.path.getmtime(filepath)
        return datetime.datetime.fromtimestamp(mtime)
    except Exception:
        return datetime.datetime.now()


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小为易读字符串 (MB / KB)"""
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def clean_expired_archives(archive_dir: Path, target_stem: str, target_suffix: str,
                           keep_days: int = 7, dry_run: bool = False) -> Tuple[int, int]:
    """
    清理归档目录中超过 keep_days 天的历史文件。
    返回: (已清理数量, 保留数量)
    """
    if not archive_dir.exists() or not archive_dir.is_dir():
        return 0, 0

    now = datetime.datetime.now()
    cutoff_time = now - datetime.timedelta(days=keep_days)
    pattern = f"{target_stem}_*{target_suffix}"

    archived_files = list(archive_dir.glob(pattern))
    deleted_count = 0
    kept_count = 0

    for f in archived_files:
        if not f.is_file():
            continue

        file_dt = get_file_datetime(f)
        if file_dt < cutoff_time:
            # 属于过期文件
            age_days = (now - file_dt).total_seconds() / 86400.0
            try:
                if not dry_run:
                    f.unlink(missing_ok=True)
                deleted_count += 1
                action_str = "[清理过期归档]" if not dry_run else "[模拟清理过期归档]"
                print(f"{action_str} {f.name} (已保留 {age_days:.1f} 天, 超过限制 {keep_days} 天)")
            except PermissionError:
                print(f"[警告] 文件被占用，跳过删除: {f.name}")
                kept_count += 1
            except Exception as e:
                print(f"[警告] 删除归档文件失败 ({f.name}): {e}")
                kept_count += 1
        else:
            kept_count += 1

    return deleted_count, kept_count


def archive_existing_file(target_file: Path, archive_dir: Path,
                          keep_days: int = 7, dry_run: bool = False) -> Optional[Path]:
    """
    若 target_file 存在，将其归档到 archive_dir，以该文件实际的修改时间作为时间戳命名。
    如果 archive_dir 中已存在同名且大小一致的副本，则跳过重复复制。
    """
    if not target_file.exists() or not target_file.is_file():
        return None

    try:
        archive_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"[警告] 无法创建归档目录 {archive_dir}: {e}")
        return None

    mtime = os.path.getmtime(target_file)
    dt = datetime.datetime.fromtimestamp(mtime)
    ts_str = dt.strftime("%Y%m%d_%H%M%S")
    target_size = os.path.getsize(target_file)

    archive_filename = f"{target_file.stem}_{ts_str}{target_file.suffix}"
    archive_path = archive_dir / archive_filename

    # 检查是否已有完全相同的备份
    if archive_path.exists() and archive_path.is_file():
        try:
            if os.path.getsize(archive_path) == target_size:
                print(f"[归档已存在] 同版本已在归档库中: {archive_path.name} ({format_file_size(target_size)})")
                return archive_path
        except Exception:
            pass

    # 执行安全复制 (保持元数据与修改时间)
    try:
        if not dry_run:
            shutil.copy2(target_file, archive_path)
        action_str = "[已成功归档]" if not dry_run else "[模拟归档]"
        print(f"{action_str} {target_file.name} -> archive\\{archive_filename} "
              f"({format_file_size(target_size)}, 时间: {dt.strftime('%Y-%m-%d %H:%M:%S')})")
        return archive_path
    except PermissionError:
        print(f"[警告] 文件正被其他进程占用，未能复制到归档库: {target_file.name}")
        return None
    except Exception as e:
        print(f"[警告] 归档过程发生异常: {e}")
        return None


def list_archived_files(archive_dir: Path, target_stem: str, target_suffix: str) -> None:
    """列出当前归档目录中保留的文件详情"""
    if not archive_dir.exists() or not archive_dir.is_dir():
        print(f"[归档库] 目录不存在: {archive_dir}")
        return

    pattern = f"{target_stem}_*{target_suffix}"
    files = list(archive_dir.glob(pattern))
    if not files:
        print(f"[归档库] 暂无 {target_stem} 的历史备份")
        return

    # 按时间降序排序
    files.sort(key=lambda x: get_file_datetime(x), reverse=True)
    print(f"\n----------- 当前保留的历史归档版本 (共 {len(files)} 个) -----------")
    for f in files:
        f_dt = get_file_datetime(f)
        try:
            sz_str = format_file_size(os.path.getsize(f))
        except Exception:
            sz_str = "未知大小"
        print(f"  * {f.name:<40} [{sz_str:>9}]  时间: {f_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print("------------------------------------------------------------------\n")


def run_stage(target_path_str: str, archive_dir_str: Optional[str] = None,
              keep_days: int = 7, stage: str = "pre-build", dry_run: bool = False) -> int:
    """
    执行指定阶段的归档任务
    """
    target_file = Path(target_path_str).resolve()
    if archive_dir_str:
        archive_dir = Path(archive_dir_str).resolve()
    else:
        archive_dir = target_file.parent / "archive"

    print(f"==========================================================")
    print(f"[构建归档管理器] 阶段: {stage} | 目标: {target_file.name} | 保留天数: 最近 {keep_days} 天")
    print(f"==========================================================")

    if stage == "pre-build":
        # 打包前阶段：若有旧文件，将其备份归档，并清理过期文件
        if target_file.exists() and target_file.is_file():
            print(f"[发现旧版本] 检测到已有打包文件: {target_file}")
            archive_existing_file(target_file, archive_dir, keep_days=keep_days, dry_run=dry_run)
        else:
            print(f"[无旧版本] 目标文件尚不存在，跳过打包前归档: {target_file.name}")

        deleted, kept = clean_expired_archives(archive_dir, target_file.stem, target_file.suffix,
                                              keep_days=keep_days, dry_run=dry_run)
        if deleted > 0:
            print(f"[生命周期清理] 已清理 {deleted} 个超过 {keep_days} 天的历史版本")
        print(f"[状态] 归档库当前保留 {kept} 个最近版本")

    elif stage == "post-build":
        # 打包完成阶段：确认新构建文件已生成，归档新版本，并清理过期
        if target_file.exists() and target_file.is_file():
            print(f"[新版本就绪] 构建成功: {target_file.name} ({format_file_size(os.path.getsize(target_file))})")
            archive_existing_file(target_file, archive_dir, keep_days=keep_days, dry_run=dry_run)
        else:
            print(f"[警告] 构建结束后未检测到目标文件: {target_file}")

        clean_expired_archives(archive_dir, target_file.stem, target_file.suffix,
                               keep_days=keep_days, dry_run=dry_run)
        list_archived_files(archive_dir, target_file.stem, target_file.suffix)

    elif stage == "clean-only":
        deleted, kept = clean_expired_archives(archive_dir, target_file.stem, target_file.suffix,
                                              keep_days=keep_days, dry_run=dry_run)
        print(f"[清理完成] 已清理: {deleted} 个, 保留: {kept} 个")
        list_archived_files(archive_dir, target_file.stem, target_file.suffix)

    elif stage == "list":
        list_archived_files(archive_dir, target_file.stem, target_file.suffix)

    print("==========================================================")
    return 0


def main():
    parser = argparse.ArgumentParser(description="PyInstaller 构建产物自动归档与生命周期清理工具")
    parser.add_argument("--spec", default=None,
                        help="自适应输入的 .spec 配置文件路径 (例如: ats.spec 或 instock_MonitorTK.spec)")
    parser.add_argument("--target", default=None,
                        help="目标构建文件路径 (若指定了 --spec 则自动从此 spec 文件推导)")
    parser.add_argument("--dist-dir", default=None,
                        help="目标构建输出目录 (默认: spec 同级或当前目录下的 dist)")
    parser.add_argument("--archive-dir", default=None,
                        help="历史归档目录 (默认: 目标目录下的 archive 文件夹)")
    parser.add_argument("--days", type=int, default=7,
                        help="保留历史归档的天数 (默认: 7 天)")
    parser.add_argument("--stage", choices=["pre-build", "post-build", "clean-only", "list"],
                        default="pre-build",
                        help="执行阶段: pre-build (打包前备份旧版), post-build (打包后快照), clean-only (仅清理), list (列出)")
    parser.add_argument("--dry-run", action="store_true",
                        help="演练模式，仅输出日志不实际读写文件")

    args = parser.parse_args()

    # 自适应解析目标 exe 路径
    dist_dir = Path(args.dist_dir).resolve() if args.dist_dir else None

    if args.spec:
        spec_path = Path(args.spec).resolve()
        target_path = resolve_target_from_spec(spec_path, dist_dir=dist_dir)
        print(f"[配置自适应] 从 spec 配置文件 ({spec_path.name}) 自动推导目标: {target_path.name}")
    elif args.target:
        # 若 --target 传入的是 .spec 文件，智能识别并推导
        if args.target.strip().lower().endswith(".spec"):
            spec_path = Path(args.target).resolve()
            target_path = resolve_target_from_spec(spec_path, dist_dir=dist_dir)
            print(f"[配置自适应] --target 传入了 spec 文件 ({spec_path.name})，自动推导目标: {target_path.name}")
        else:
            target_path = Path(args.target).resolve()
    else:
        # 两者均未显式指定，默认 ATS_Terminal.exe
        target_path = Path("dist/ATS_Terminal.exe").resolve()

    try:
        sys.exit(run_stage(
            target_path_str=str(target_path),
            archive_dir_str=args.archive_dir,
            keep_days=args.days,
            stage=args.stage,
            dry_run=args.dry_run
        ))
    except Exception as e:
        # 绝不让辅助归档脚本由于任何未知异常中断外层批处理构建
        print(f"[归档管理器非致命异常] {e}", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
