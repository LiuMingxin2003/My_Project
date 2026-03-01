
#唬人的加密系统！！！！！！！！！！！！！！！！！！！！！！
#唬人的加密系统！！！！！！！！！！！！！！！！！！！！！！
#唬人的加密系统！！！！！！！！！！！！！！！！！！！！！！
#唬人的加密系统！！！！！！！！！！！！！！！！！！！！！！
#唬人的加密系统！！！！！！！！！！！！！！！！！！！！！！

import tkinter as tk
from tkinter import ttk
import uuid

# 配色方案
COLORS = {
    "bg": "#1A1A1A",
    "text": "#FFFFFF",
    "accent": "#00FF88",
    "secondary": "#2D2D2D",
    "progress_bg": "#151515"
}


def generate_machine_code():
    mac = uuid.getnode()
    return '-'.join(f"{mac:012X}"[i:i + 2] for i in range(0, 12, 2))


class GeneratorApp:
    def __init__(self, root):
        self.root = root
        self.setup_ui()
        self.messages = [
            "初始化系统......[OK]",
            "验证硬件签名......[完成]",
            "随机生成密钥......[加密]",
            "加密中......[通过]",
            "同步到服务器中......[成功]"
        ]
        self.current_step = 0
        self.total_steps = len(self.messages)

    def setup_ui(self):
        self.root.title("安全标识生成系统")
        self.root.geometry("400x280")
        self.root.configure(bg=COLORS["bg"])

        # 自定义样式
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TProgressbar",
                        thickness=24,
                        troughcolor=COLORS["progress_bg"],
                        bordercolor=COLORS["bg"],
                        lightcolor=COLORS["accent"],
                        darkcolor=COLORS["accent"]
                        )

        # 界面组件
        self.header = tk.Label(self.root,
                               text="令牌加密系统",
                               font=("Segoe UI", 16, "bold"),
                               bg=COLORS["bg"],
                               fg=COLORS["accent"]
                               )
        self.header.pack(pady=(20, 15))

        self.code_display = tk.Text(self.root,
                                    height=2,
                                    width=45,
                                    font=("Consolas", 10),
                                    bg=COLORS["secondary"],
                                    fg=COLORS["accent"],
                                    relief='flat'
                                    )
        self.code_display.config(state='disabled')
        self.code_display.pack()

        self.progress_bar = ttk.Progressbar(self.root,
                                            orient='horizontal',
                                            length=380,
                                            mode='determinate'
                                            )
        self.progress_bar.pack(pady=15)

        self.progress_label = tk.Label(self.root,
                                       text="等待启动...",
                                       font=("Microsoft YaHei", 9),
                                       bg=COLORS["bg"],
                                       fg=COLORS["text"]
                                       )
        self.progress_label.pack()

        self.start_btn = ttk.Button(self.root,
                                    text="启动加密",
                                    command=self.start_process,
                                    style='TButton'
                                    )
        self.start_btn.pack(pady=10)

    def start_process(self):
        self.start_btn.config(state='disabled')
        self.current_step = 0
        self.progress_bar['value'] = 0
        self.update_progress()

    def update_progress(self):
        if self.current_step < self.total_steps:
            # 计算进度百分比
            progress = (self.current_step + 1) / self.total_steps * 100
            increment = progress - self.progress_bar['value']

            # 更新界面
            self.progress_label.config(
                text=self.messages[self.current_step],
                fg=COLORS["accent"]
            )
            self.progress_bar['value'] += increment
            self.current_step += 1

            # 控制速度（每步800ms）
            self.root.after(800, self.update_progress)
        else:
            # 完成时显示机器码
            self.progress_bar['value'] = 100
            self.code_display.config(state='normal')
            self.code_display.delete(1.0, tk.END)
            self.code_display.insert(tk.END, generate_machine_code())
            self.code_display.config(state='disabled')
            self.progress_label.config(text="安全标识生成完成！")
            self.start_btn.config(state='normal')


if __name__ == "__main__":
    root = tk.Tk()
    app = GeneratorApp(root)
    root.mainloop()