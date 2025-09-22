import win32api
import win32con
import win32gui
from ahk import AHK
import time
def broadcast_stock_code(stock_code,message_type='stock'):
    if str(message_type) == 'stock':
        if str(stock_code)[0] in ['0','3','1']:
            codex = '6' + str(stock_code)
        elif str(stock_code)[0] in ['6','5']:
            codex = '7' + str(stock_code)
        # elif str(stock_code)[0] == '9':
        #     codex = '2' + str(stock_code)
        else:
            codex = '4' + str(stock_code)
    else:
        codex = int(stock_code)
    UWM_STOCK = win32api.RegisterWindowMessage('stock')
    print(win32con.HWND_BROADCAST,UWM_STOCK,int(codex))
    #系统广播
    win32gui.PostMessage( win32con.HWND_BROADCAST,UWM_STOCK,int(codex),0)

def send_message(subHandle):
    UWM_STOCK = win32api.RegisterWindowMessage('stock')
    print(win32con.HWND_BROADCAST,UWM_STOCK,int(codex))
    #系统广播
    win32gui.PostMessage( win32con.HWND_BROADCAST,UWM_STOCK,int(codex),0)
    
    # # 获取窗口文本不含截尾空字符的长度
    # # 参数：窗口句柄； 消息类型； 参数WParam； 参数IParam
    # bufSize = win32api.SendMessage(subHandle, win32con.WM_GETTEXTLENGTH, 0, 0) +1
    # # 利用api生成Buffer
    # strBuf = win32gui.PyMakeBuffer(bufSize)
    # print(strBuf)
    # # 发送消息获取文本内容
    # # 参数：窗口句柄； 消息类型；文本大小； 存储位置
    # length = win32gui.SendMessage(subHandle, win32con.WM_GETTEXT, bufSize, strBuf)
    # # 反向内容，转为字符串
    # # text = str(strBuf[:-1])
    # address, length = win32gui.PyGetBufferAddressAndLen(strBuf) 
    # text = win32gui.PyGetString(address, length) 
    # # print('text: ', text)
def send_dfcf(code):
    ahk = AHK()
    applist=['东方财富']
    for window in ahk.list_windows():
        for app in applist:
            if window.title.find(app) >= 0:
                print(f'class_name:{window.get_class()}')
                print(f'title:{window.title}')
                # Some more attributes
                # print(f'text:{window.text}')
                # print(window.text)           # window text -- or .get_text()
                print(window.get_position()) # (x, y, width, height)
                print(window.id)             # the ahk_id of the window
                print(window.pid)            # process ID -- or .get_pid()
                print(window.process_path)   # or .get_process_path()
                print('....................\n\n')
                window.activate()
                # ahk.setKeyDelay(50)
                ahk.send(code)
                time.sleep(0.2)
                ahk.send('{Enter}')

if __name__ == '__main__':
    # broadcast_stock_code('999999')
    # broadcast_stock_code('000001')
    code='159775'
    code='002905'
    code='301446'
    broadcast_stock_code(code)
    # broadcast_stock_code(code,message_type='etf')
    # send_dfcf(code)


# import pymem
# import pymem.process
# import win32gui
# import win32api
# import win32con
# import re
# #导入完模块

# pointer_offset = 0x0
# #获取同花顺的实时代码
# def get_ths_code(OffsetAdd):
#     #进程层
#     GetGameProcess=pymem.Pymem("hexin.exe")
#     #获取同花顺的基址
#     GetGameModuleProcess=pymem.process.module_from_name(GetGameProcess.process_handle, "hexin.exe").lpBaseOfDll
#     ReadGameMemory=GetGameProcess.read_int(GetGameModuleProcess+OffsetAdd)
#     print(ReadGameMemory)

#     data = GetGameProcess.read_bytes(ReadGameMemory, 7)
#     # GetGameProcess.read_string(pointer_address + pointer_offset, 7)
#     str1=data.decode('utf-8')
#     print(f'str1:{str1}')
#     #字符串拆分成由单个字母组成的列表：
#     strlist=list(str1)
#     strlist.pop(0) # 删除下标为0的字符
#     Stock_code="".join(strlist)
#     print(strlist)
#     print("实时股票代码:"+ Stock_code)
#     return strlist

# # 向通达信广播股票代码
# def BroadCast(Message, Code):
#     if str(Message)=='Stock':
#         if str(Code)[0]=='6':
#             codex='7'+str(Code)
#             print(codex)
#         else:
#             codex='6'+str(Code)
#     else:
#         # codex=int(Code)
#         codex='4'+str(Code)
#     UWM_STOCK = win32api.RegisterWindowMessage('Stock')
#     win32gui.PostMessage(win32con.HWND_BROADCAST,UWM_STOCK,int(codex),0)

# # 获取同花顺金融大师的实时股票代码

# # Stock_code="".join(get_ths_code(0x017160E8))
# # Stock_code="".join(get_ths_code(0x0192D21C))
# # print(Stock_code)

# # 0x017160E8
# # 0x0150E228
# # 0x015568F4
# # 获取同花顺免费版的实时股票代码
# # Stock_code="".join(get_ths_code(0x0150E228))
# # BroadCast('Stock', Stock_code)