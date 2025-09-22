import win32pipe, win32file
import tkinter as tk

def send_code_via_pipe(code):
    """
    通过命名管道向服务器发送代码。
    :param code: 要发送的代码字符串。
    :return: 发送成功返回 True，否则返回 False。
    """
    # 定义管道的名称，必须与服务器端的名称一致
    pipe_name = r"\\.\pipe\my_named_pipe"
    
    try:
        # 打开管道进行写入
        handle = win32file.CreateFile(
            pipe_name,
            win32file.GENERIC_WRITE, # 写入权限
            0, None,
            win32file.OPEN_EXISTING, # 必须已经存在
            0, None
        )
        # 将代码编码为UTF-8字节并写入管道
        win32file.WriteFile(handle, code.encode("utf-8"))
        # 关闭管道句柄
        # win32file.CloseHandle(handle)
        return True
    except Exception as e:
        # 如果出现错误，打印错误信息
        print(f"管道发送错误: {e}")
        return False

class SenderApp:
    def __init__(self, master):
        """
        初始化发送方 Tkinter 应用程序。
        """
        self.master = master
        self.master.title("代码发送 (管道)") # 设置窗口标题

        # 创建并打包标签以显示提示信息
        self.label = tk.Label(master, text="要发送的代码:")
        self.label.pack(pady=10)

        # 创建并打包输入框
        self.entry = tk.Entry(master, width=30)
        self.entry.pack(pady=5)
        self.entry.insert(0, "600519") # 设置默认值

        # 创建并打包发送按钮，并绑定 send_code 方法
        self.send_button = tk.Button(master, text="发送", command=self.send_code)
        self.send_button.pack(pady=10)

        # 创建并打包标签以显示发送状态
        self.status_label = tk.Label(master, text="")
        self.status_label.pack(pady=5)

    def send_code(self):
        """
        处理发送按钮的点击事件。
        """
        code = self.entry.get() # 获取输入框中的代码
        if send_code_via_pipe(code):
            # 如果发送成功，更新状态标签
            self.status_label.config(text=f"发送成功: {code}", fg="green")
        else:
            # 如果发送失败，更新状态标签
            self.status_label.config(text="发送失败", fg="red")

if __name__ == '__main__':
    # 创建 Tkinter 主窗口
    root = tk.Tk()
    sender_app = SenderApp(root)
    # 启动主事件循环
    root.mainloop()

    # send_code_via_pipe('655335')
