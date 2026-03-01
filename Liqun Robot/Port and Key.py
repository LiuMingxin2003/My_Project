import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import os


class ServerConfigApp:
    def __init__(self):
        # 创建主窗口
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # 无边框窗口
        self.root.geometry("400x300+500+200")  # 窗口大小和初始位置

        # 创建画布用于渐变背景
        self.canvas = tk.Canvas(self.root, width=400, height=300)
        self.canvas.pack()

        # 绘制渐变背景
        self.draw_gradient("#348F50", "#56B4D3")

        # 添加界面组件
        self.create_widgets()

        # 添加关闭按钮
        self.add_close_button()

        # 添加窗口拖动支持
        self.canvas.bind("<ButtonPress-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.on_move)

        self.root.mainloop()

    def draw_gradient(self, start_color, end_color):
        """绘制渐变背景"""
        for y in range(300):
            r = int((y / 300) * int(end_color[1:3], 16) + (1 - y / 300) * int(start_color[1:3], 16))
            g = int((y / 300) * int(end_color[3:5], 16) + (1 - y / 300) * int(start_color[3:5], 16))
            b = int((y / 300) * int(end_color[5:7], 16) + (1 - y / 300) * int(start_color[5:7], 16))
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.canvas.create_line(0, y, 400, y, fill=color)

    def create_widgets(self):
        """创建输入组件"""
        # 端口输入框
        # API密钥输入框
        self.lbl_api_key = ttk.Label(self.root, text="API密钥:",
                                     foreground="white", background="#348F50")
        self.lbl_api_key.place(relx=0.3, rely=0.3, anchor="e")

        self.ent_api_key = ttk.Entry(self.root, show="*", width=20)
        self.ent_api_key.place(relx=0.5, rely=0.3, anchor="center")

        self.lbl_port = ttk.Label(self.root, text="服务端口:",
                                  foreground="white", background="#348F50")
        self.lbl_port.place(relx=0.3, rely=0.4, anchor="e")

        self.ent_port = ttk.Entry(self.root, width=20)
        self.ent_port.insert(0, "4200")  # 设置默认值
        self.ent_port.place(relx=0.5, rely=0.4, anchor="center")

        # 确认按钮
        self.btn_confirm = ttk.Button(self.root, text="启动服务",
                                      command=self.save_config)
        self.btn_confirm.place(relx=0.5, rely=0.6, anchor="center", width=120)

    def add_close_button(self):
        """添加关闭按钮"""
        close_btn = tk.Label(self.root, text="×", font=("Arial", 18),
                             fg="white", bg="#348F50")
        close_btn.place(relx=0.98, rely=0.02, anchor="ne")
        close_btn.bind("<Button-1>", lambda e: self.root.destroy())

    def start_move(self, event):
        """窗口拖动开始"""
        self.x = event.x
        self.y = event.y

    def on_move(self, event):
        """窗口拖动过程"""
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def validate_input(self):
        """验证输入有效性"""
        port = self.ent_port.get()

        try:
            port = int(port)
            if not (1024 <= port <= 65535):  # 限制特权端口
                raise ValueError
            return True
        except ValueError:
            messagebox.showerror("错误", "端口号必须为1024-65535之间的整数")
            return False

    def save_config(self):
        """保存配置到文件并启动服务"""
        if not self.validate_input():
            return

        config_content = f"""SERVER_CONFIG = {{
    "host": "0.0.0.0",  # 监听所有网络接口
    "port": "{self.ent_port.get()}",
    "API":"{self.ent_api_key.get()}",
    "debug": False  # 生产环境关闭调试模式
}}


"""
        try:
            # 写入配置文件
            with open("renew_config.py", "w", encoding="utf-8") as f:
                f.write(config_content)

            # 执行服务启动文件
            if os.path.exists("Interface.py"):
                subprocess.Popen(["python", "Interface.py"])
                self.root.destroy()  # 关闭配置窗口
            else:
                messagebox.showerror("错误", "未找到服务文件 Interface")

        except Exception as e:
            messagebox.showerror("错误", f"配置保存失败: {str(e)}")


if __name__ == "__main__":
    ServerConfigApp()