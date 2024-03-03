# Code to check if left or right mouse buttons were pressed 
import win32api 
import time 
# import pyperclip
import win32con
import win32gui

import sys
sys.path.append("..")
# from JSONData import tdx_data_Day as tdd
# from JohnsonUtil import LoggerFactory as LoggerFactory
# from JohnsonUtil import johnson_cons as ct
from JohnsonUtil import commonTips as cct


state_left = win32api.GetKeyState(0x01)  # Left button down = 0 or 1. Button up = -127 or -128 
state_right = win32api.GetKeyState(0x02)  # Right button down = 0 or 1. Button up = -127 or -128 

double_click_flag = False
global time_s
global mouse_click_count
time_s=0
mouse_click_count = 0
click_timeout = 0.3
right_click_timeout = 2

VK_CODE = {
    'backspace': 0x08,
    'tab': 0x09,
    'clear': 0x0C,
    'enter': 0x0D,
    'shift': 0x10,
    'ctrl': 0x11,
    'alt': 0x12,
    'pause': 0x13,
    'caps_lock': 0x14,
    'esc': 0x1B,
    'spacebar': 0x20,
    'page_up': 0x21,
    'page_down': 0x22,
    'end': 0x23,
    'home': 0x24,
    'left_arrow': 0x25,
    'up_arrow': 0x26,
    'right_arrow': 0x27,
    'down_arrow': 0x28,
    'select': 0x29,
    'print': 0x2A,
    'execute': 0x2B,
    'print_screen': 0x2C,
    'ins': 0x2D,
    'del': 0x2E,
    'help': 0x2F,
    '0': 0x30,
    '1': 0x31,
    '2': 0x32,
    '3': 0x33,
    '4': 0x34,
    '5': 0x35,
    '6': 0x36,
    '7': 0x37,
    '8': 0x38,
    '9': 0x39,
    'a': 0x41,
    'b': 0x42,
    'c': 0x43,
    'd': 0x44,
    'e': 0x45,
    'f': 0x46,
    'g': 0x47,
    'h': 0x48,
    'i': 0x49,
    'j': 0x4A,
    'k': 0x4B,
    'l': 0x4C,
    'm': 0x4D,
    'n': 0x4E,
    'o': 0x4F,
    'p': 0x50,
    'q': 0x51,
    'r': 0x52,
    's': 0x53,
    't': 0x54,
    'u': 0x55,
    'v': 0x56,
    'w': 0x57,
    'x': 0x58,
    'y': 0x59,
    'z': 0x5A,
    'numpad_0': 0x60,
    'numpad_1': 0x61,
    'numpad_2': 0x62,
    'numpad_3': 0x63,
    'numpad_4': 0x64,
    'numpad_5': 0x65,
    'numpad_6': 0x66,
    'numpad_7': 0x67,
    'numpad_8': 0x68,
    'numpad_9': 0x69,
    'multiply_key': 0x6A,
    'add_key': 0x6B,
    'separator_key': 0x6C,
    'subtract_key': 0x6D,
    'decimal_key': 0x6E,
    'divide_key': 0x6F,
    'F1': 0x70,
    'F2': 0x71,
    'F3': 0x72,
    'F4': 0x73,
    'F5': 0x74,
    'F6': 0x75,
    'F7': 0x76,
    'F8': 0x77,
    'F9': 0x78,
    'F10': 0x79,
    'F11': 0x7A,
    'F12': 0x7B,
    'F13': 0x7C,
    'F14': 0x7D,
    'F15': 0x7E,
    'F16': 0x7F,
    'F17': 0x80,
    'F18': 0x81,
    'F19': 0x82,
    'F20': 0x83,
    'F21': 0x84,
    'F22': 0x85,
    'F23': 0x86,
    'F24': 0x87,
    'num_lock': 0x90,
    'scroll_lock': 0x91,
    'left_shift': 0xA0,
    'right_shift ': 0xA1,
    'left_control': 0xA2,
    'right_control': 0xA3,
    'left_menu': 0xA4,
    'right_menu': 0xA5,
    'browser_back': 0xA6,
    'browser_forward': 0xA7,
    'browser_refresh': 0xA8,
    'browser_stop': 0xA9,
    'browser_search': 0xAA,
    'browser_favorites': 0xAB,
    'browser_start_and_home': 0xAC,
    'volume_mute': 0xAD,
    'volume_Down': 0xAE,
    'volume_up': 0xAF,
    'next_track': 0xB0,
    'previous_track': 0xB1,
    'stop_media': 0xB2,
    'play/pause_media': 0xB3,
    'start_mail': 0xB4,
    'select_media': 0xB5,
    'start_application_1': 0xB6,
    'start_application_2': 0xB7,
    'attn_key': 0xF6,
    'crsel_key': 0xF7,
    'exsel_key': 0xF8,
    'play_key': 0xFA,
    'zoom_key': 0xFB,
    'clear_key': 0xFE,
    '+': 0xBB,
    ',': 0xBC,
    '-': 0xBD,
    '.': 0xBE,
    '/': 0xBF,
    '`': 0xC0,
    ';': 0xBA,
    '[': 0xDB,
    '\\': 0xDC,
    ']': 0xDD,
    "'": 0xDE,
    '`': 0xC0}

def key_esc():
    win32api.keybd_event(VK_CODE["esc"], 0, 0, 0)
    time.sleep(0.02)
    win32api.keybd_event(VK_CODE["esc"], 0, win32con.KEYEVENTF_KEYUP, 0)
    # win32api.keybd_event(VK_CODE['spacebar'], 0,0,0)
    # win32api.keybd_event(VK_CODE['spacebar'],0 ,win32con.KEYEVENTF_KEYUP ,0)

# ctrl+c
def key_copy():
    win32api.keybd_event(VK_CODE["ctrl"], 0, 0, 0)
    time.sleep(0.01)
    win32api.keybd_event(VK_CODE["c"], 0, 0, 0)
    win32api.keybd_event(VK_CODE["c"], 0, win32con.KEYEVENTF_KEYUP, 0)
    win32api.keybd_event(VK_CODE["ctrl"], 0, win32con.KEYEVENTF_KEYUP, 0)

# def get_content():
#     content = pyperclip.paste()
#     print("content:",content)
#     return content

def mouse_click():
    '''  delay mouse action to allow for double click to occur
    '''
    global time_s
    global mouse_click_count
    # aw.after(300, mouse_action, event)
    mouse_click_count = +1
    # print("mouse_click_count: time_s:",mouse_click_count,time_s)
    if time_s == 0:
        mouse_click_count = 1
        time_s = time.time()
    else:
        time_t = round(time.time() - time_s,3)
        if time_t > click_timeout:
            time_s = 0
            mouse_click_count = 0
            if mouse_click_count > 0:
                double_click_flag = False
        elif mouse_click_count > 1:
            double_click_flag = False

    # return time_s

def double_click():
    '''  set the double click status flag
    '''
    global double_click_flag
    global time_s
    time_t = round(time.time() - time_s,3)
    # print("leftclick:",time_t)
    if 0.05 < time_t < click_timeout:
        double_click_flag = True
        # print("double_click")
        # time_s = round(time.time(),3)
    else:
        if time_t > click_timeout:
            double_click_flag = False
            mouse_click_count = 0
            time_s = 0

def right_click():
    '''  set the double click status flag
    '''
    global double_click_flag
    global time_s
    if double_click_flag:
        time_t = round(time.time() - time_s,3)
        # print("right:",time_t)
        if time_t < right_click_timeout:
            print("right_click to copy time_s:",time_t)
            key_esc()
            time.sleep(0.02)
            key_copy()
            time_s=0
        else:
            double_click_flag = False
            # print("right_click no copy:",time_t)
            time_s=0

def mouse_action(event):
    global double_click_flag
    if double_click_flag:
        print('double mouse click event')
        double_click_flag = False
    else:
        print('single mouse click event')

def on_click(x, y, button, pressed):
    if pressed == True:
        take_screenshot()
    elif pressed == False:
        pass




def main():
    while True: 
        a = win32api.GetKeyState(0x01) 
        b = win32api.GetKeyState(0x02) 
     
        if a != state_left:  # Button state changed 
            state_left = a 
            # print("state_left:",a) 
            if a < 0: 
                time_t = round(time.time() - time_s,3)
                if time_t > click_timeout:
                    mouse_click_count = 0
                    time_s = 0
                    double_click_flag = False
                # if time_s == 0:
                #     mouse_click()
                # print('Left Button Pressed') 
            else:
                if time_s == 0:
                    mouse_click()
                elif mouse_click_count == 1:
                    double_click()
                # print('Left Button Released') 
     
        if b != state_right:  # Button state changed 
            state_right = b 
            # print("state_right:",b) 
            if b < 0: 
                pass
                # print('Right Button Pressed') 
            else: 
                if double_click_flag and mouse_click_count == 1:
                    right_click()
                # print('Right Button Released') 
        time.sleep(0.001) 

if __name__ == '__main__':
    # search_ths_data('000006')

    if cct.isMac():
        width, height = 80, 22
        cct.set_console(width, height)
    else:
        width, height = 80, 22
        cct.set_console(width, height)
    # main()
    while True: 
        a = win32api.GetKeyState(0x01) 
        b = win32api.GetKeyState(0x02) 
     
        if a != state_left:  # Button state changed 
            state_left = a 
            # print("state_left:",a) 
            if a < 0: 
                time_t = round(time.time() - time_s,3)
                if time_t > click_timeout:
                    mouse_click_count = 0
                    time_s = 0
                    double_click_flag = False
                # if time_s == 0:
                #     mouse_click()
                # print('Left Button Pressed') 
            else:
                if time_s == 0:
                    mouse_click()
                elif mouse_click_count == 1:
                    double_click()
                # print('Left Button Released') 
     
        if b != state_right:  # Button state changed 
            state_right = b 
            # print("state_right:",b) 
            if b < 0: 
                pass
                # print('Right Button Pressed') 
            else: 
                if double_click_flag and mouse_click_count == 1:
                    right_click()
                # print('Right Button Released') 
        time.sleep(0.001) 