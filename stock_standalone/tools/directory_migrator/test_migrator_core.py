# -*- coding: utf-8 -*-
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import migrator_core
import app as migrator_app
from migrator_core import (
    MigrationError,
    TreeEntry,
    TreeInventory,
    TreeMismatchError,
    build_preflight_report,
    compare_inventories,
    inspect_tree,
    migrate_directory,
    validate_paths,
)


def _make_symlink_or_skip(test_case, target, link, is_directory=False):
    try:
        os.symlink(str(target), str(link), target_is_directory=is_directory)
    except (OSError, NotImplementedError) as exc:
        test_case.skipTest("当前 Windows 环境未授予创建符号链接的权限：{}".format(exc))


class AppCloseTests(unittest.TestCase):
    def test_read_only_scan_can_close_without_waiting(self):
        instance = migrator_app.DirectoryMigratorApp.__new__(
            migrator_app.DirectoryMigratorApp
        )
        instance.busy = True
        instance.active_kind = "occupancy"
        instance.cancel_event = threading.Event()
        instance.root = mock.Mock()

        with mock.patch.object(migrator_app.messagebox, "showinfo") as showinfo:
            instance._on_close()

        self.assertTrue(instance.cancel_event.is_set())
        instance.root.destroy.assert_called_once_with()
        showinfo.assert_not_called()

    def test_preflight_shows_occupants_and_skips_full_result_display(self):
        instance = migrator_app.DirectoryMigratorApp.__new__(
            migrator_app.DirectoryMigratorApp
        )
        instance.root = mock.Mock()
        instance.status_var = mock.Mock()
        instance._append_log = mock.Mock()
        instance._append_occupant_lines = mock.Mock()
        occupants = [{"pid": 321, "name": "Holder.exe"}]
        report = {
            "source": "C:\\source",
            "destination": "E:\\migrated",
            "inventory": None,
            "occupants": occupants,
        }

        with mock.patch.object(migrator_app.messagebox, "showwarning") as warning:
            instance._show_preflight(report)

        instance._append_occupant_lines.assert_called_once_with(occupants)
        self.assertIn("Holder.exe (PID 321)", warning.call_args.args[1])
        instance.status_var.set.assert_called_once_with(
            "预检查已提前停止：请先关闭占用程序。"
        )


class InventoryTests(unittest.TestCase):
    def test_preflight_stops_after_finding_source_occupant(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            destination = Path(temp) / "migrated"
            source.mkdir()
            occupant = [{"pid": 321, "name": "Holder.exe"}]

            with mock.patch.object(
                migrator_core, "find_source_occupants", return_value=occupant
            ) as check_occupants, mock.patch.object(
                migrator_core, "inspect_tree"
            ) as scan_tree, mock.patch.object(
                migrator_core, "_check_volume_and_space"
            ) as check_space:
                report = build_preflight_report(str(source), str(destination))

            check_occupants.assert_called_once()
            scan_tree.assert_not_called()
            check_space.assert_not_called()
            self.assertIsNone(report["inventory"])
            self.assertEqual(report["occupants"], occupant)

    def test_preflight_stops_when_source_cannot_be_renamed(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            destination = Path(temp) / "migrated"
            source.mkdir()

            with mock.patch.object(
                migrator_core, "_check_source_rename_access",
                side_effect=migrator_core.SourceInUseError("目录句柄占用"),
            ) as check_rename, mock.patch.object(
                migrator_core, "_restart_manager_occupants"
            ) as check_files, mock.patch.object(
                migrator_core, "inspect_tree"
            ) as scan_tree:
                with self.assertRaisesRegex(
                    migrator_core.SourceInUseError, "目录句柄占用"
                ):
                    build_preflight_report(str(source), str(destination))

            check_rename.assert_called_once()
            check_files.assert_not_called()
            scan_tree.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows 目录句柄测试")
    def test_rename_probe_detects_process_current_directory_handle(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            process = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=str(source),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                time.sleep(0.2)
                with mock.patch.object(
                    migrator_core, "_restart_manager_occupants", return_value=[]
                ):
                    with self.assertRaisesRegex(
                        migrator_core.SourceInUseError, "目录句柄"
                    ):
                        migrator_core._check_source_rename_access(str(source))
            finally:
                process.terminate()
                process.wait(timeout=5)

    @unittest.skipUnless(os.name == "nt", "Windows 子目录句柄测试")
    def test_occupancy_scan_detects_process_cwd_in_nested_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            nested = source / "nested" / "deeper"
            nested.mkdir(parents=True)
            destination = Path(temp) / "migrated"
            process = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                cwd=str(nested),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                time.sleep(0.2)
                def scan_resources(resource_paths, **_kwargs):
                    list(resource_paths)
                    return []

                with mock.patch.object(
                    migrator_core, "_restart_manager_occupants",
                    side_effect=scan_resources,
                ) as restart_manager:
                    with self.assertRaisesRegex(
                        migrator_core.SourceInUseError, "nested.*deeper"
                    ):
                        migrate_directory(
                            str(source), str(destination),
                            confirm_apps_closed=True,
                        )

                self.assertTrue(restart_manager.called)
                self.assertFalse(destination.exists())
                self.assertTrue(nested.is_dir())
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_occupancy_scan_streams_entries_and_observes_cancellation(self):
        class Entry:
            def __init__(self, path):
                self.path = path

        class Scanner:
            def __init__(self, entries):
                self.entries = iter(entries)
                self.yielded = 0

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def __iter__(self):
                for entry in self.entries:
                    self.yielded += 1
                    yield entry

        entries = [Entry("source\\file-{}.dat".format(index)) for index in range(100)]
        scanner = Scanner(entries)
        cancel_event = threading.Event()
        with mock.patch.object(migrator_core.os, "scandir", return_value=scanner), \
                mock.patch.object(migrator_core.os, "lstat", return_value=mock.Mock(st_mode=0)), \
                mock.patch.object(migrator_core, "_reparse_kind", return_value=None), \
                mock.patch.object(migrator_core.stat, "S_ISDIR", return_value=False), \
                mock.patch.object(migrator_core.stat, "S_ISREG", return_value=True):
            resources = migrator_core._iter_source_resources("source", cancel_event)
            self.assertEqual(next(resources), entries[0].path)
            self.assertEqual(scanner.yielded, 1)
            cancel_event.set()
            with self.assertRaises(migrator_core.MigrationCancelled):
                next(resources)
            self.assertLessEqual(scanner.yielded, 2)

    def test_inventory_and_copy_preserve_internal_and_external_links(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            stage = base / "stage"
            destination = base / "destination"
            external_config = base / "outside" / "mcp_config.json"
            (source / "log").mkdir(parents=True)
            external_config.parent.mkdir()
            (source / "log" / "cli-1.log").write_text("log data", encoding="utf-8")
            external_config.write_text('{"ok": true}', encoding="utf-8")
            _make_symlink_or_skip(
                self, "log/cli-1.log", source / "cli.log"
            )
            _make_symlink_or_skip(
                self, str(external_config), source / "mcp_config.json"
            )
            _make_symlink_or_skip(
                self, "log", source / "log-shortcut", is_directory=True
            )

            inventory = inspect_tree(str(source))
            migrator_core._copy_tree(
                str(source), str(stage), str(destination), inventory
            )
            copied = inspect_tree(str(stage))
            compare_inventories(inventory, copied)
            self.assertEqual(
                os.readlink(str(stage / "cli.log")), os.path.join("log", "cli-1.log")
            )
            self.assertEqual(
                Path(os.path.realpath(str(stage / "mcp_config.json"))),
                external_config,
            )
            self.assertTrue(os.path.isdir(str(stage / "log-shortcut")))

    def test_occupancy_scan_does_not_follow_file_or_directory_symlinks(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            logs = source / "logs"
            external = base / "outside"
            logs.mkdir(parents=True)
            external.mkdir()
            (logs / "cli.log").write_text("log data", encoding="utf-8")
            (external / "mcp_config.json").write_text("{}", encoding="utf-8")
            _make_symlink_or_skip(self, "logs/cli.log", source / "cli.log")
            _make_symlink_or_skip(
                self, str(external / "mcp_config.json"), source / "mcp_config.json"
            )
            _make_symlink_or_skip(
                self, str(external), source / "external-link", is_directory=True
            )

            resources = {
                os.path.normcase(path)
                for path in migrator_core._iter_source_resources(str(source))
            }

            self.assertEqual(resources, {os.path.normcase(str(logs / "cli.log"))})

    def test_compare_reports_hash_mismatch(self):
        expected = TreeInventory(
            root="source",
            entries={
                "data.bin": TreeEntry(
                    relative_path="data.bin",
                    kind="file",
                    size=3,
                    sha256="abc",
                )
            },
            total_bytes=3,
        )
        actual = TreeInventory(
            root="target",
            entries={
                "data.bin": TreeEntry(
                    relative_path="data.bin",
                    kind="file",
                    size=3,
                    sha256="def",
                )
            },
            total_bytes=3,
        )
        with self.assertRaisesRegex(TreeMismatchError, "sha256"):
            compare_inventories(expected, actual)

    def test_rejects_special_fifo_without_following_it(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("当前平台不支持 FIFO")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            os.mkfifo(str(root / "pipe"))
            with self.assertRaisesRegex(
                migrator_core.UnsupportedEntryError, "特殊文件"
            ):
                inspect_tree(str(root))

    def test_preserves_hardlink_group_inside_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            stage = base / "stage"
            source.mkdir()
            (source / "one.bin").write_bytes(b"same inode")
            try:
                os.link(str(source / "one.bin"), str(source / "two.bin"))
            except OSError as exc:
                self.skipTest("当前文件系统不支持硬链接：{}".format(exc))
            inventory = inspect_tree(str(source))
            migrator_core._copy_tree(
                str(source), str(stage), str(base / "destination"), inventory
            )
            copied = inspect_tree(str(stage))
            compare_inventories(inventory, copied)
            self.assertEqual(
                os.stat(str(stage / "one.bin")).st_ino,
                os.stat(str(stage / "two.bin")).st_ino,
            )

    def test_rejects_hardlink_to_file_outside_selected_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            source.mkdir()
            (source / "inside.bin").write_bytes(b"shared")
            try:
                os.link(str(source / "inside.bin"), str(base / "outside.bin"))
            except OSError as exc:
                self.skipTest("当前文件系统不支持硬链接：{}".format(exc))
            with self.assertRaisesRegex(
                migrator_core.UnsupportedEntryError, "以外的硬链接"
            ):
                inspect_tree(str(source))

    @unittest.skipUnless(os.name == "nt", "NTFS 备用数据流测试")
    def test_rejects_alternate_data_stream(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            file_path = root / "state.txt"
            file_path.write_text("visible stream", encoding="utf-8")
            try:
                with open(str(file_path) + ":codex-test", "wb") as stream:
                    stream.write(b"hidden stream")
            except OSError as exc:
                self.skipTest("当前卷不支持 NTFS 备用数据流：{}".format(exc))
            with self.assertRaisesRegex(
                migrator_core.UnsupportedEntryError, "备用数据流"
            ):
                inspect_tree(str(root))


@unittest.skipUnless(os.name == "nt", "Windows 卷信息 API 测试")
class VolumeCompatibilityTests(unittest.TestCase):
    def test_ramdisk_volume_path_falls_back_to_drive_root(self):
        ctypes = migrator_core.ctypes
        kernel32 = mock.Mock()

        def invalid_function(*_args):
            ctypes.set_last_error(1)
            return 0

        def return_ntfs(_path, _name, _name_size, _serial, _max_component,
                        _flags, fs_name, _fs_name_size):
            fs_name.value = "NTFS"
            return 1

        kernel32.GetVolumePathNameW.side_effect = invalid_function
        kernel32.GetVolumeNameForVolumeMountPointW.side_effect = invalid_function
        kernel32.GetVolumeInformationW.side_effect = return_ntfs

        with mock.patch.object(ctypes, "WinDLL", return_value=kernel32):
            filesystem = migrator_core._windows_filesystem(r"G:\PPTAI")

        self.assertEqual(filesystem, "NTFS")
        self.assertEqual(
            kernel32.GetVolumeInformationW.call_args.args[0], "G:\\"
        )


class PathValidationTests(unittest.TestCase):
    def test_rejects_existing_destination_without_touching_source(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            destination = base / "destination"
            source.mkdir()
            destination.mkdir()
            with self.assertRaisesRegex(MigrationError, "已存在"):
                validate_paths(str(source), str(destination))
            self.assertTrue(source.is_dir())
            self.assertTrue(destination.is_dir())

    def test_rejects_target_inside_source(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            destination_parent = source / "nested"
            destination_parent.mkdir()
            with self.assertRaisesRegex(MigrationError, "源目录内部"):
                validate_paths(
                    str(source), str(destination_parent / "moved")
                )

    @unittest.skipUnless(os.name == "nt", "Windows 目录联接路径测试")
    def test_rejects_destination_parent_junction_into_source(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            alias = base / "source-alias"
            source.mkdir()
            migrator_core._create_junction(str(alias), str(source))
            try:
                with self.assertRaisesRegex(MigrationError, "链接解析后发生重叠"):
                    validate_paths(str(source), str(alias / "moved"))
            finally:
                os.rmdir(alias)


class MigrationTransactionTests(unittest.TestCase):
    def _fake_junction(self, link, target):
        os.symlink(target, link, target_is_directory=True)

    def test_success_cleans_backup_only_after_full_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            destination = base / "migrated"
            source.mkdir()
            (source / "state.json").write_text('{"x":1}', encoding="utf-8")
            (source / "log").mkdir()
            (source / "log" / "cli.log").write_text("ok", encoding="utf-8")
            external_config = base / "config" / "mcp_config.json"
            external_config.parent.mkdir()
            external_config.write_text('{"keep": true}', encoding="utf-8")
            _make_symlink_or_skip(self, "log/cli.log", source / "cli.log")
            _make_symlink_or_skip(
                self, str(external_config), source / "mcp_config.json"
            )

            result = migrate_directory(
                str(source),
                str(destination),
                confirm_apps_closed=True,
                junction_factory=self._fake_junction,
                platform_checks=False,
            )
            self.assertTrue(result.backup_cleaned)
            self.assertTrue(source.is_symlink())
            self.assertTrue(os.path.samefile(str(source), str(destination)))
            self.assertFalse(os.path.lexists(result.backup))
            self.assertEqual(
                os.readlink(str(destination / "cli.log")),
                os.path.join("log", "cli.log"),
            )
            self.assertTrue(external_config.is_file())
            self.assertEqual(
                Path(os.path.realpath(str(destination / "mcp_config.json"))),
                external_config,
            )

    def test_rename_probe_failure_stops_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            destination = Path(temp) / "migrated"
            source.mkdir()
            (source / "state.json").write_text("original", encoding="utf-8")

            with mock.patch.object(
                migrator_core, "_check_source_rename_access",
                side_effect=migrator_core.SourceInUseError("目录句柄占用"),
            ), mock.patch.object(migrator_core, "_copy_tree") as copy_tree:
                with self.assertRaisesRegex(
                    migrator_core.SourceInUseError, "目录句柄占用"
                ):
                    migrate_directory(
                        str(source), str(destination), confirm_apps_closed=True
                    )

            copy_tree.assert_not_called()
            self.assertEqual(
                (source / "state.json").read_text(encoding="utf-8"), "original"
            )
            self.assertFalse(destination.exists())

    def test_cutover_error_reports_verified_destination_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            destination = Path(temp) / "migrated"
            source.mkdir()
            (source / "state.json").write_text("original", encoding="utf-8")
            real_replace = os.replace
            source_norm = os.path.normcase(os.path.abspath(str(source)))

            def fail_source_rename(src, dst):
                if os.path.normcase(os.path.abspath(str(src))) == source_norm:
                    error = OSError("Access is denied")
                    error.winerror = 5
                    raise error
                return real_replace(src, dst)

            with mock.patch.object(migrator_core.os, "replace", side_effect=fail_source_rename):
                with self.assertRaises(MigrationError) as raised:
                    migrate_directory(
                        str(source),
                        str(destination),
                        confirm_apps_closed=True,
                        junction_factory=self._fake_junction,
                        platform_checks=False,
                    )

            self.assertIn("已核验通过的目标副本保留", str(raised.exception))
            self.assertTrue(source.is_dir())
            self.assertFalse(source.is_symlink())
            self.assertTrue(destination.is_dir())
            self.assertEqual(
                (source / "state.json").read_text(encoding="utf-8"), "original"
            )
            self.assertEqual(
                (destination / "state.json").read_text(encoding="utf-8"),
                "original",
            )

    def test_final_verification_failure_restores_source_and_skips_cleanup(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            destination = base / "migrated"
            source.mkdir()
            (source / "state.json").write_text('{"safe": true}', encoding="utf-8")

            real_compare = migrator_core.compare_inventories
            call_count = {"value": 0}

            def fail_final_comparison(expected, actual):
                call_count["value"] += 1
                if call_count["value"] == 4:
                    raise TreeMismatchError("测试注入：最终核验差异")
                return real_compare(expected, actual)

            with mock.patch.object(
                migrator_core, "compare_inventories",
                side_effect=fail_final_comparison,
            ), mock.patch.object(
                migrator_core, "_cleanup_backup"
            ) as cleanup:
                with self.assertRaisesRegex(MigrationError, "原目录恢复"):
                    migrate_directory(
                        str(source),
                        str(destination),
                        confirm_apps_closed=True,
                        junction_factory=self._fake_junction,
                        platform_checks=False,
                    )
            cleanup.assert_not_called()
            self.assertTrue(source.is_dir())
            self.assertFalse(source.is_symlink())
            self.assertEqual(
                (source / "state.json").read_text(encoding="utf-8"),
                '{"safe": true}',
            )
            self.assertTrue(destination.is_dir())

    def test_cleanup_failure_keeps_verified_junction_and_reports_backup(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            destination = Path(temp) / "migrated"
            source.mkdir()
            (source / "state.json").write_text("safe", encoding="utf-8")

            with mock.patch.object(
                migrator_core, "_cleanup_backup",
                side_effect=MigrationError("测试注入：清理失败"),
            ):
                result = migrate_directory(
                    str(source),
                    str(destination),
                    confirm_apps_closed=True,
                    junction_factory=self._fake_junction,
                    platform_checks=False,
                )

            self.assertFalse(result.backup_cleaned)
            self.assertIn("清理失败", result.cleanup_error)
            self.assertTrue(os.path.islink(str(source)))
            self.assertTrue(os.path.samefile(str(source), str(destination)))
            self.assertEqual(
                (Path(result.backup) / "state.json").read_text(encoding="utf-8"),
                "safe",
            )

    def test_requires_closed_application_confirmation(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            destination = Path(temp) / "migrated"
            source.mkdir()
            with self.assertRaisesRegex(MigrationError, "关闭"):
                migrate_directory(
                    str(source),
                    str(destination),
                    junction_factory=self._fake_junction,
                    platform_checks=False,
                )
            self.assertTrue(source.is_dir())

    def test_occupied_source_stops_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            destination = Path(temp) / "migrated"
            source.mkdir()
            (source / "state.json").write_text("safe", encoding="utf-8")
            occupant = [{"pid": 321, "name": "Holder.exe"}]

            with mock.patch.object(
                migrator_core, "find_source_occupants", return_value=occupant
            ) as check_occupants:
                with self.assertRaisesRegex(
                    migrator_core.SourceInUseError, "Holder.exe.*321"
                ):
                    migrate_directory(
                        str(source), str(destination), confirm_apps_closed=True
                    )

            check_occupants.assert_called_once()
            self.assertEqual((source / "state.json").read_text(encoding="utf-8"), "safe")
            self.assertFalse(destination.exists())

    @unittest.skipUnless(os.name == "nt", "Windows 目录联接集成测试")
    def test_occupant_found_before_cutover_removes_verified_target(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            destination = Path(temp) / "migrated"
            source.mkdir()
            (source / "state.json").write_text("safe", encoding="utf-8")
            occupant = [{"pid": 654, "name": "LateHolder.exe"}]

            with mock.patch.object(
                migrator_core, "find_source_occupants",
                side_effect=[[], occupant],
            ) as check_occupants:
                with self.assertRaisesRegex(
                    migrator_core.SourceInUseError, "LateHolder.exe.*654"
                ):
                    migrate_directory(
                        str(source), str(destination), confirm_apps_closed=True
                    )

            self.assertEqual(check_occupants.call_count, 2)
            self.assertTrue(source.is_dir())
            self.assertFalse(source.is_symlink())
            self.assertEqual((source / "state.json").read_text(encoding="utf-8"), "safe")
            self.assertFalse(os.path.lexists(destination))
            self.assertFalse(any(Path(temp).glob("source.migration-backup-*")))

    @unittest.skipUnless(os.name == "nt", "Windows 目录联接集成测试")
    def test_real_windows_junction_transaction(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source%TEMP%"
            destination = base / "migrated%TEMP%"
            source.mkdir()
            logs = source / "logs"
            logs.mkdir()
            (logs / "cli-current.log").write_text(
                "junction test", encoding="utf-8"
            )
            external_config = base / "shared" / "mcp_config.json"
            external_config.parent.mkdir()
            external_config.write_text('{"safe": true}', encoding="utf-8")
            _make_symlink_or_skip(self, "logs/cli-current.log", source / "cli.log")
            _make_symlink_or_skip(
                self, str(external_config), source / "mcp_config.json"
            )
            migrator_core._create_junction(
                str(source / "logs-link"), str(logs)
            )
            with mock.patch.object(
                migrator_core, "find_source_occupants", return_value=[]
            ) as check_occupants:
                result = migrate_directory(
                    str(source),
                    str(destination),
                    confirm_apps_closed=True,
                )
            self.assertEqual(check_occupants.call_count, 2)
            self.assertTrue(result.backup_cleaned)
            self.assertTrue(migrator_core._is_junction(str(source)))
            self.assertTrue(os.path.samefile(str(source), str(destination)))
            self.assertEqual(
                (destination / "logs" / "cli-current.log").read_text(encoding="utf-8"),
                "junction test",
            )
            self.assertTrue(os.path.samefile(
                str(destination / "logs-link"), str(destination / "logs")
            ))
            self.assertTrue(external_config.is_file())
            self.assertEqual(
                Path(os.path.realpath(str(destination / "mcp_config.json"))),
                external_config,
            )


if __name__ == "__main__":
    unittest.main()
