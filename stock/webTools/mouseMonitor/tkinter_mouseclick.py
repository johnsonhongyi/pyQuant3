from tkinter import *

def mouse_click(event):
    '''  delay mouse action to allow for double click to occur
    '''
    aw.after(300, mouse_action, event)

def double_click(event):
    '''  set the double click status flag
    '''
    global double_click_flag
    double_click_flag = True

def mouse_action(event):
    global double_click_flag
    if double_click_flag:
        print('double mouse click event')
        double_click_flag = False
    else:
        print('single mouse click event')

root = Tk()
aw = Canvas(root, width=200, height=100, bg='grey')
aw.place(x=0, y=0)

double_click_flag = False
aw.bind('<Button-1>', mouse_click) # bind left mouse click
aw.bind('<Double-1>', double_click) # bind double left clicks
aw.mainloop()