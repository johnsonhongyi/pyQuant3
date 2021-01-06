# -*- encoding: utf-8 -*-
print("abc")
import sys
sys.path.append("..")
# import JohnsonUtil.johnson_cons as ct
from JohnsonUtil import LoggerFactory

log = LoggerFactory.log
from JohnsonUtil import commonTips as cct
from JohnsonUtil import johnson_cons as ct
import random
import numpy as np
import subprocess
log = LoggerFactory.log
import gc
global RAMDISK_KEY, INIT_LOG_Error
RAMDISK_KEY = 0
INIT_LOG_Error = 0
# Compress_Count = 1
BaseDir = cct.get_ramdisk_dir()

from JSONData import tdx_hdf5_api as h5a
from JSONData import realdatajson as rl

# fix bytes to str
# pytorch_gpu\lib\codecs.py
# def write(self, object):

#         """ Writes the object's contents encoded to self.stream.
#         """
#         data, consumed = self.encode(object, self.errors)
#         if isinstance(data,bytes):
#             data = data.decode()
#         self.stream.write(data)




import sys
from threading import Thread
from PyQt5.QtWidgets import QApplication

from pyqtconsole.console import PythonConsole

app = QApplication([])
console = PythonConsole()
console.show()
console.eval_in_thread()

sys.exit(app.exec_())





# from PyQt5.QtWidgets import QApplication, QWidget
# a = QApplication([])
# wi = QWidget()
# wi.show()
# wi.hide()
# # w.raise_()
import ipdb;ipdb.set_trace()


import platform
import sys

from PyQt5 import QtCore, QtGui, QtWidgets


class NativeMessenger(QtCore.QObject):
    messageChanged = QtCore.pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.m_qin = QtCore.QFile()

        self.m_qin.open(
            sys.stdin.fileno(), QtCore.QIODevice.ReadOnly | QtCore.QIODevice.Unbuffered
        )

        if platform.system() == "Windows":
            import win32api

            if sys.platform == "win32":
                import os
                import msvcrt

                if platform.python_implementation() == "PyPy":
                    os.fdopen(fh.fileno(), "wb", 0)
                else:
                    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)

            self.m_notifier = QtCore.QWinEventNotifier(
                win32api.GetStdHandle(win32api.STD_INPUT_HANDLE)
            )

        else:
            self.m_notifier = QtCore.QSocketNotifier(
                sys.stdin.fileno(), QtCore.QSocketNotifier.Read, self
            )

        self.m_notifier.activated.connect(self.readyRead)

    @QtCore.pyqtSlot()
    def readyRead(self):
        line = self.m_qin.readLine().data().decode().strip()
        self.messageChanged.emit(line)


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)

    w = QtWidgets.QLabel(alignment=QtCore.Qt.AlignCenter)
    w.resize(640, 480)
    w.show()

    messenger = NativeMessenger()
    messenger.messageChanged.connect(w.setText)

    sys.exit(app.exec_())

import ipdb;ipdb.set_trace()



import asyncio
 
import time
 
 
 
now = lambda: time.time()
 
async def do_some_work(x):
 
    print('Waiting: {}s'.format(x))
 
 
 
    await asyncio.sleep(x)
 
    return 'Done after {}s'.format(x)
 
 
 
async def main():
 
    coroutine1 = do_some_work(1)
 
    coroutine2 = do_some_work(5)
 
    coroutine3 = do_some_work(3)
 
 
 
    tasks = [
 
        asyncio.ensure_future(coroutine1),
 
        asyncio.ensure_future(coroutine2),
 
        asyncio.ensure_future(coroutine3)
 
    ]
 
    done, pending = await asyncio.wait(tasks)
 
    for task in done:
 
        print('Task ret: ', task.result())
 
 
 
start = now()
 
 
 
loop = asyncio.get_event_loop()
 
task = asyncio.ensure_future(main())
 
try:
 
    loop.run_until_complete(task)
 
    print('TIME: ', now() - start)
 
except KeyboardInterrupt as e:
 
    print(asyncio.Task.all_tasks())
 
    print(asyncio.gather(*asyncio.Task.all_tasks()).cancel())
 
    loop.stop()
 
    loop.run_forever()
 
finally:
 
    loop.close()






import numpy as np
import pandas as pd
####生成9000,0000条数据，9千万条
# a = np.random.standard_normal((90000000,4))
a = np.random.standard_normal((9000,4))
b = pd.DataFrame(a)
# ####普通格式存储：
h5 = pd.HDFStore('G:\\test_s.h5','w')
h5['all'] = b
h5.close()


fname=['test_s.h5','sina_data.h5', 'tdx_last_df', 'powerCompute.h5', 'get_sina_all_ratio']
fname=['test_s.h5']
# fname = 'powerCompute.h5'
for na in fname:
    log.error("tdx_hd5:%s"%(na))
    with h5a.SafeHDFStore(na) as h5:
        import ipdb;ipdb.set_trace()
        print(h5)
        if '/' + 'all' in list(h5.keys()):
            print(h5['all'].loc['600007'])


####压缩格式存储
# h5 = pd.HDFStore('G:\\test_s.h5','w', complevel=4, complib='blosc')
# h5['data'] = b
# h5.close()