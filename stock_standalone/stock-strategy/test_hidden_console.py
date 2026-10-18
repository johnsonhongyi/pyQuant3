"""Windows hidden-console inheritance and bounded process cleanup."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from ats.llm.cli_process import BoundedCLIError, run_bounded_cli


@unittest.skipUnless(os.name == "nt", "Windows console semantics")
class HiddenConsoleTests(unittest.TestCase):
    def test_manager_process_launch_and_child_create_no_console_without_backend(self):
        from webTools.window_manager.antigravity_bridge_manager import AntigravityBridgeController
        probe = (
            "import ctypes,json; k=ctypes.windll.kernel32; u=ctypes.windll.user32; "
            "k.GetConsoleWindow.restype=ctypes.c_void_p; u.IsWindowVisible.argtypes=[ctypes.c_void_p]; "
            "w=k.GetConsoleWindow(); print(json.dumps({'console':w,'visible':bool(u.IsWindowVisible(w))}),flush=True)"
        )
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            worker = root / "fake_worker.py"
            worker.write_text(probe + "; import subprocess,sys,time; subprocess.run([sys.executable,'-c',"
                + repr(probe) + "],check=True); time.sleep(1)", encoding="utf-8")
            controller = AntigravityBridgeController(root)
            controller.preference_path = root / "preferences.json"
            processes = []
            original = subprocess.Popen
            def launch(*args, **kwargs):
                process = original(*args, **kwargs)
                processes.append(process)
                return process
            with patch.object(controller, "bridge_command", return_value=[sys.executable, str(worker)]), \
                 patch.object(controller, "task_info", return_value={"running": False}), \
                 patch("webTools.window_manager.antigravity_bridge_manager.subprocess.Popen", side_effect=launch):
                self.assertEqual(controller._start_bridge(run_mode="process"), "started")
                processes[0].wait(timeout=5)
            rows = [json.loads(line) for line in (controller.runtime_path() / "agent-output.txt").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertFalse(rows[0]["console"])
            self.assertFalse(rows[1]["console"])
            self.assertFalse(any(row["visible"] for row in rows))

    def test_root_and_child_share_one_hidden_console_with_pipes_intact(self):
        probe = (
            "import ctypes,json; k=ctypes.windll.kernel32; u=ctypes.windll.user32; "
            "k.GetConsoleWindow.restype=ctypes.c_void_p; u.IsWindowVisible.argtypes=[ctypes.c_void_p]; "
            "w=k.GetConsoleWindow(); print(json.dumps({'console':w,'visible':bool(u.IsWindowVisible(w))}),flush=True)"
        )
        parent = probe + "; import subprocess,sys; subprocess.run([sys.executable,'-c',sys.argv[1]],check=True)"
        with tempfile.TemporaryDirectory() as folder:
            result = run_bounded_cli([sys.executable, "-c", parent, probe], cwd=folder,
                stdin_bytes=b"", timeout_seconds=5, hidden_console=True)
        rows = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["console"])
        self.assertEqual(rows[0]["console"], rows[1]["console"])
        self.assertFalse(any(row["visible"] for row in rows))

    def test_default_callers_keep_no_window_and_agv_hidden_mode_is_opt_in(self):
        original = subprocess.Popen
        flags = []
        def launch(*args, **kwargs):
            flags.append(kwargs["creationflags"])
            self.assertTrue(kwargs["startupinfo"].dwFlags & subprocess.STARTF_USESHOWWINDOW)
            self.assertEqual(kwargs["startupinfo"].wShowWindow, subprocess.SW_HIDE)
            return original(*args, **kwargs)
        with tempfile.TemporaryDirectory() as folder, patch("ats.llm.cli_process.subprocess.Popen", side_effect=launch):
            for hidden in (False, True):
                run_bounded_cli([sys.executable, "-c", "print('ok')"], cwd=folder,
                    stdin_bytes=b"", timeout_seconds=5, hidden_console=hidden)
        self.assertTrue(flags[0] & subprocess.CREATE_NO_WINDOW)
        self.assertEqual(flags[1], subprocess.CREATE_NEW_CONSOLE)
        self.assertFalse(flags[1] & subprocess.CREATE_NO_WINDOW)

    def test_hidden_console_timeout_reaps_owned_child(self):
        import psutil
        output = bytearray()
        code = ("import subprocess,sys,time; "
                "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)']); "
                "print(p.pid,flush=True); time.sleep(20)")
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(BoundedCLIError, "CLI_TIMEOUT"):
                run_bounded_cli([sys.executable, "-c", code], cwd=folder, stdin_bytes=b"",
                    timeout_seconds=1, hidden_console=True, stdout_callback=output.extend)
        child_pid = int(bytes(output).strip())
        self.assertFalse(psutil.pid_exists(child_pid))


if __name__ == "__main__":
    unittest.main()
