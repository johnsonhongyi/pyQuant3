"""Discovery cannot block dispatch and its owned child exits on cancellation."""
import os
import subprocess
import sys
import threading
import time
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from desktop_runtime import DesktopRuntimeProbe, _discovery_output, desktop_cli


class DesktopRuntimeTests(unittest.TestCase):
    def test_managed_current_engine_precedes_old_installs_but_respects_override(self):
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory)
            managed=home/'packages/app-server-daemon/current/bin/codex.exe'
            managed.parent.mkdir(parents=True)
            managed.touch()
            explicit=home/'custom.exe';explicit.touch()
            fallback=home/'fallback.exe';fallback.touch()
            with patch.dict('os.environ',{'CODEX_HOME':str(home),'LOCALAPPDATA':str(home),'CODEX_CLI_PATH':''}), \
                 patch('ats.llm.cli_paths.shutil.which',return_value=str(fallback)) as lookup:
                self.assertEqual(os.path.normcase(desktop_cli()),
                                 os.path.normcase(str(managed.absolute())))
                lookup.assert_not_called()
                with patch.dict('os.environ',{'CODEX_CLI_PATH':str(explicit)}):
                    self.assertEqual(os.path.normcase(desktop_cli()),os.path.normcase(str(explicit.absolute())))
                managed.unlink()
                self.assertEqual(os.path.normcase(desktop_cli()),os.path.normcase(str(fallback.absolute())))

    def test_desktop_exported_versioned_path_does_not_pin_old_engine(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            legacy=root/'OpenAI/Codex/bin/old-version/codex.exe'
            managed=root/'packages/app-server-daemon/current/bin/codex.exe'
            for path in (legacy,managed):path.parent.mkdir(parents=True);path.touch()
            with patch.dict('os.environ',{'LOCALAPPDATA':str(root),'CODEX_HOME':str(root),
                                          'CODEX_CLI_PATH':str(legacy)}):
                self.assertEqual(os.path.normcase(desktop_cli()),
                                 os.path.normcase(str(managed.absolute())))

    def test_slow_probe_never_blocks_snapshot_or_shutdown(self):
        entered=threading.Event()
        def blocked(stop):
            entered.set()
            stop.wait(5)
            return {'status':'unavailable'}
        probe=DesktopRuntimeProbe(probe=blocked)
        try:
            self.assertTrue(entered.wait(1))
            started=time.monotonic()
            self.assertEqual(probe.snapshot()['status'],'discovering')
            self.assertLess(time.monotonic()-started,0.1)
        finally:probe.close()
        self.assertFalse(probe.thread.is_alive())

    def test_cancel_reaps_real_discovery_child(self):
        stop=threading.Event()
        spawned=[]
        spawn=subprocess.Popen
        def child(*args,**kwargs):
            process=spawn([sys.executable,'-c','import time;time.sleep(30)'],**kwargs)
            spawned.append(process)
            return process
        errors=[]
        def run():
            try:_discovery_output('unused',stop)
            except InterruptedError:errors.append('cancelled')
        with patch('desktop_runtime.subprocess.Popen',side_effect=child):
            worker=threading.Thread(target=run)
            worker.start()
            deadline=time.monotonic()+2
            while not spawned and time.monotonic()<deadline:time.sleep(0.01)
            stop.set()
            worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors,['cancelled'])
        self.assertIsNotNone(spawned[0].poll())


if __name__=='__main__':unittest.main()
