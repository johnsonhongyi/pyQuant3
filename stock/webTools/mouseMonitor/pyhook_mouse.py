# -*- coding: UTF8 -*-

import PyHook3
import pythoncom
import threading

time_k = 0;

def execute_script(time_k_old, action):
    '''
     作用：执行脚本
    '''
    try:
        global time_k
        
        if(time_k ==1):
            print(action + "单击动作")
        elif(time_k == 2):
            print(action + "双击动作")
            
    except Exception as e:
        print(e)
    
    time_k = 0;
    
# 监听到鼠标事件调用
def onMouseEvent(event):
    global m
    global time_k;
    try:
        if(event.MessageName != "mouse move"  and (event.MessageName == "mouse left up" or event.MessageName == "mouse right up")):   # 因为鼠标一动就会有很多mouse move，所以把这个过滤下，鼠标按下和抬起都会有记录，这里我们把抬起down操作过滤掉
            
            action = ""   # 记录左键还是右键点击
            if("right" in event.MessageName):
                action = "右键"
            elif("left" in event.MessageName):
                action = "左键"
                
            if(time_k == 0):
                time_k = 1;
                # 设定1秒后延迟执行
                threading.Timer(1, execute_script, (time_k, action)).start()
            elif(time_k == 1):
                time_k = 2;
            elif(time_k == 2):
                return False
                
        return True # 为True才会正常调用，如果为False的话，此次事件被拦截
    except Exception as e:
        print(e)

# 监听到键盘事件调用
def onKeyboardEvent(event):
    # print(event.Key)   # 返回按下的键
    return True

def main():
    # 创建管理器
    hm = PyHook3.HookManager()
    # 监听键盘
    hm.KeyDown = onKeyboardEvent   
    hm.HookKeyboard()  
    # 监听鼠标 
    hm.MouseAll = onMouseEvent   
    hm.HookMouse()
    # 循环监听
    pythoncom.PumpMessages() 
 
if __name__ == "__main__":
    main()# -*- coding: UTF8 -*-

import PyHook3
import pythoncom
import threading

time_k = 0;

def execute_script(time_k_old, action):
    '''
     作用：执行脚本
    '''
    try:
        global time_k
        
        if(time_k ==1):
            print(action + "单击动作")
        elif(time_k == 2):
            print(action + "双击动作")
            
    except Exception as e:
        print(e)
    
    time_k = 0;
    
# 监听到鼠标事件调用
def onMouseEvent(event):
    global m
    global time_k;
    try:
        if(event.MessageName != "mouse move"  and (event.MessageName == "mouse left up" or event.MessageName == "mouse right up")):   # 因为鼠标一动就会有很多mouse move，所以把这个过滤下，鼠标按下和抬起都会有记录，这里我们把抬起down操作过滤掉
            
            action = ""   # 记录左键还是右键点击
            if("right" in event.MessageName):
                action = "右键"
            elif("left" in event.MessageName):
                action = "左键"
                
            if(time_k == 0):
                time_k = 1;
                # 设定1秒后延迟执行
                threading.Timer(1, execute_script, (time_k, action)).start()
            elif(time_k == 1):
                time_k = 2;
            elif(time_k == 2):
                return False
                
        return True # 为True才会正常调用，如果为False的话，此次事件被拦截
    except Exception as e:
        print(e)

# 监听到键盘事件调用
def onKeyboardEvent(event):
    # print(event.Key)   # 返回按下的键
    return True

def main():
    # 创建管理器
    hm = PyHook3.HookManager()
    # 监听键盘
    hm.KeyDown = onKeyboardEvent   
    hm.HookKeyboard()  
    # 监听鼠标 
    hm.MouseAll = onMouseEvent   
    hm.HookMouse()
    # 循环监听
    pythoncom.PumpMessages() 
 
if __name__ == "__main__":
    main()