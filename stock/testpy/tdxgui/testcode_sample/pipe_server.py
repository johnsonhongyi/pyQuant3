import win32pipe, win32file
import threading
import tkinter as tk
import time

def pipe_server_thread(app):
    """
    运行命名管道服务器的线程函数。
    """
    # 定义命名管道的名称，客户端和服务器必须使用相同的名称
    pipe_name = r"\\.\pipe\my_named_pipe"
    
    # 创建命名管道
    pipe = win32pipe.CreateNamedPipe(
        pipe_name,
        # 管道访问模式：双向读写
        win32pipe.PIPE_ACCESS_DUPLEX,
        # 管道操作模式：消息模式（一次性传输一个完整消息），阻塞读写，支持无限实例
        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
        # 允许无限实例连接
        win32pipe.PIPE_UNLIMITED_INSTANCES, 
        65536, 65536, 0, None
    )
    
    print("管道服务器正在等待客户端连接...")
    
    try:
        while True:
            # 阻塞等待客户端连接
            win32pipe.ConnectNamedPipe(pipe, None)
            
            try:
                # 循环读取来自当前连接客户端的数据
                while True:
                    # 从管道中读取数据，返回一个元组 (错误码, 读取到的字节数据)
                    # 读取65536字节的数据
                    error_code, resp_bytes = win32file.ReadFile(pipe, 65536)
                    
                    # 检查是否成功读取以及数据是否为空
                    if error_code == 0 and resp_bytes:
                        # 对字节数据进行UTF-8解码
                        code = resp_bytes.decode("utf-8")
                        print(f"通过管道接收: {code}")
                        # 将接收到的消息安全地传递给 Tkinter 应用程序
                        # app.receive_message(code)
                        app(code)
                    else:
                        # 如果没有数据或者客户端断开连接，则跳出内层循环
                        break
            except Exception as e:
                # 捕获读取过程中的任何错误，例如客户端异常断开
                print(f"读取数据时出错: {e}")
            finally:
                # 无论内部循环如何结束，都断开与当前客户端的连接
                win32pipe.DisconnectNamedPipe(pipe)
                
    except Exception as e:
        # 捕获创建或连接管道时的任何错误
        print(f"管道服务器运行中出现严重错误: {e}")
    finally:
        # 确保在程序结束时关闭管道句柄
        win32file.CloseHandle(pipe)

# class ReceiverApp:
#     # ... (Tkinter GUI部分的代码保持不变)
#     def __init__(self, master):
#         self.master = master
#         self.master.title("异动联动 - 接收方 (管道)")
#         self.master.geometry("400x200")
#         self.label = tk.Label(master, text="等待消息...", font=("Arial", 16))
#         self.label.pack(pady=20, padx=20)
#         self.last_message_label = tk.Label(master, text="", font=("Arial", 12))
#         self.last_message_label.pack(pady=10)

#     def receive_message(self, code):
#         """
#         在 Tkinter 主线程中安全地更新 GUI。
#         """
#         # 使用 after 方法将 GUI 更新操作放入 Tkinter 的事件队列
#         self.master.after(0, lambda: self.label.config(text=f"已接收: {code}"))
#         self.master.after(0, lambda: self.last_message_label.config(text=f"最后接收: {code}"))

# if __name__ == '__main__':
#     root = tk.Tk()
#     receiver_app = ReceiverApp(root)
    
#     # 在守护线程中启动管道服务器，以免阻塞主事件循环
#     server_thread = threading.Thread(target=pipe_server_thread, args=(receiver_app,), daemon=True)
#     server_thread.start()
    
#     root.mainloop()


PIPE_NAME = r"\\.\pipe\my_named_pipe"

def pipe_server(update_callback):
    """
    命名管道服务器线程
    """
    pipe = win32pipe.CreateNamedPipe(
        PIPE_NAME,
        win32pipe.PIPE_ACCESS_DUPLEX,
        win32pipe.PIPE_TYPE_MESSAGE | win32pipe.PIPE_READMODE_MESSAGE | win32pipe.PIPE_WAIT,
        win32pipe.PIPE_UNLIMITED_INSTANCES,
        65536, 65536, 0, None
    )
    print("管道服务器启动，等待连接...")

    while True:
        win32pipe.ConnectNamedPipe(pipe, None)
        try:
            while True:
                err, data = win32file.ReadFile(pipe, 65536)
                # print(f'err : {err} data :{data}')
                if err == 0 and data:
                    code = data.decode("utf-8")
                    update_callback(code)
                else:
                    print(f'err : {err} data :{data}')
                    break
        except Exception as e:
            print("读取数据异常:", e)
        finally:
            print("DisconnectNamedPipe:")
            win32pipe.DisconnectNamedPipe(pipe)

def aprint_(code):
    print(f'code : {code}')


pipe_server_thread(aprint_)