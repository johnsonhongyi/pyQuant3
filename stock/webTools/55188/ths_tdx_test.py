import pymem
import pymem.process
import win32gui
import win32api
import win32con
import re
#导入完模块
#获取同花顺的实时代码
def get_ths_code(OffsetAdd):
    #进程层
    GetGameProcess=pymem.Pymem("hexin.exe")
    #获取同花顺的基址
    GetGameModuleProcess=pymem.process.module_from_name(GetGameProcess.process_handle, "hexin.exe").lpBaseOfDll
    ReadGameMemory=GetGameProcess.read_int(GetGameModuleProcess+OffsetAdd)
    print(ReadGameMemory)
    data = GetGameProcess.read_bytes(ReadGameMemory, 7)
    str1=data.decode('utf-8')
    #字符串拆分成由单个字母组成的列表：
    strlist=list(str1)
    strlist.pop(0) # 删除下标为0的字符
    Stock_code="".join(strlist)
    print(strlist)
    print("实时股票代码:"+ Stock_code)
    return strlist
# 向通达信广播股票代码
def BroadCast(Message, Code):
    if str(Message)=='Stock':
        if str(Code)[0]=='6':
            codex='7'+str(Code)
            print(codex)
        else:
            codex='6'+str(Code)
    else:
        codex=int(Code)
    UWM_STOCK = win32api.RegisterWindowMessage('Stock')
    win32gui.PostMessage(win32con.HWND_BROADCAST,UWM_STOCK,int(codex),0)
# 获取同花顺金融大师的实时股票代码
Stock_code="".join(get_ths_code(0x015568F4))
# 获取同花顺免费版的实时股票代码
BroadCast('Stock', '000001')
# Stock_code="".join(get_ths_code(0x0150E228))
print(Stock_code)
