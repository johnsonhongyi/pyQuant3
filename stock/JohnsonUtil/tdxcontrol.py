import win32api
import win32con
import win32gui

def broadcast_stock_code(stock_code,message_type='stock'):


    if str(message_type) == 'stock':
        if str(stock_code)[0] in ('0','3'):
            codex = '6' + str(stock_code)
        elif str(stock_code)[0] == '6':
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


if __name__ == '__main__':
    # broadcast_stock_code('999999')
    # broadcast_stock_code('000001')
    broadcast_stock_code('833171')