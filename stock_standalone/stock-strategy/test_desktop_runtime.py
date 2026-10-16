"""Discovery cannot block dispatch and its owned child exits on cancellation."""
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
from desktop_runtime import DesktopRuntimeProbe, _discovery_output


class DesktopRuntimeTests(unittest.TestCase):
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
