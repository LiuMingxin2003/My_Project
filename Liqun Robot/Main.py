import os
import tkinter as tk
from tkinter import ttk
import uuid
import random
import subprocess
class AuthApp:
    def __init__(self):
        # 创建主窗口
        self.root = tk.Tk()
        self.root.overrideredirect(True)  # 无边框窗口
        self.root.geometry("400x300+500+200")  # 窗口大小和初始位置

        # 预设授权码（需要替换为实际值）
        self.authorized_code = "F0-9E-4A-AD-BE-2B"  # 示例，请替换为真实机器码

        # 创建画布用于渐变背景
        self.canvas = tk.Canvas(self.root, width=400, height=300)
        self.canvas.pack()

        # 绘制渐变背景
        self.draw_gradient("#348F50", "#56B4D3")

        # 添加关闭按钮
        self.add_close_button()

        # 添加验证标签
        self.verify_label = tk.Label(self.root, text="验证中...",
                                     font=("微软雅黑", 14),
                                     fg="white", bg="#348F50")
        self.verify_label.place(relx=0.5, rely=0.4, anchor="center")

        # 添加进度条
        self.progress = ttk.Progressbar(self.root, orient="horizontal",
                                        length=250, mode="determinate")
        self.progress.place(relx=0.5, rely=0.5, anchor="center")

        # 添加窗口拖动支持
        self.canvas.bind("<ButtonPress-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.on_move)

        # 开始进度条动画
        self.start_progress()

        self.root.mainloop()

    def draw_gradient(self, start_color, end_color):
        """绘制渐变背景"""
        for y in range(300):
            r = int((y / 300) * int(end_color[1:3], 16) + (1 - y / 300) * int(start_color[1:3], 16))
            g = int((y / 300) * int(end_color[3:5], 16) + (1 - y / 300) * int(start_color[3:5], 16))
            b = int((y / 300) * int(end_color[5:7], 16) + (1 - y / 300) * int(start_color[5:7], 16))
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.canvas.create_line(0, y, 400, y, fill=color)

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

    def start_progress(self):
        """启动进度条动画"""
        duration = random.randint(1, 3)  # 随机1-3秒
        steps = 100
        interval = duration * 1000 // steps

        self.progress["value"] = 0
        self.progress["maximum"] = 100
        self.update_progress(0, steps, interval)

    def update_progress(self, current, total_steps, interval):
        """更新进度条"""
        if current <= total_steps:
            self.progress["value"] = (current / total_steps) * 100
            self.root.after(interval,
                            self.update_progress,
                            current + 1, total_steps, interval)
        else:
            self.check_authorization()

    def generate_machine_code(self):
        mac = uuid.getnode()
        return '-'.join(f"{mac:012X}"[i:i + 2] for i in range(0, 12, 2))
    def check_authorization(self):
        """验证机器码"""
        machine_code = self.generate_machine_code()  # 获取机器码
        print(machine_code)
        if machine_code == self.authorized_code:
            self.show_welcome()
            # 执行授权文件（示例）
            subprocess.Popen(["python", "Port and key.py"])
        else:
            self.verify_label.config(text="制作不易，未授权")
            self.root.after(2000, self.root.destroy)

    def show_welcome(self):
        """显示欢迎信息"""
        welcome_label = tk.Label(self.root, text="欢迎使用",
                                 font=("微软雅黑", 55),
                                 fg="white", bg="#348F50")
        welcome_label.place(relx=0.5, rely=0.5, anchor="center")


if __name__ == "__main__":
    # 使用前需要：
    # 1. 运行一次获取实际机器码：print(uuid.getnode())
    # 2. 将authorized_code替换为实际值
    # 3. 准备好要执行的authorized.py文件
    AuthApp()
    os._exit(0)