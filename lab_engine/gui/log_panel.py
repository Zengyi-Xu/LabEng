"""带颜色标签的日志面板。"""
import tkinter as tk
from tkinter import ttk

from lab_engine.gui.shell import COLOR_CARD, COLOR_TEXT, MONO_FONT


class LogPanel(ttk.Frame):
    """日志显示面板。"""

    def __init__(self, parent, height: int = 12):
        super().__init__(parent)
        self._setup_ui(height)

    def _setup_ui(self, height: int):
        frame = tk.Frame(self, bg=COLOR_CARD)
        frame.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(
            frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            height=height,
            font=(MONO_FONT, 9),
            bg="#0F172A",
            fg="#E2E8F0",
            bd=0,
            highlightthickness=0,
            insertbackground="#E2E8F0",
        )
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)

        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.text.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.configure(yscrollcommand=sb.set)

        self.text.tag_configure("info", foreground="#E2E8F0")
        self.text.tag_configure("warn", foreground="#FBBF24")
        self.text.tag_configure("error", foreground="#F87171")
        self.text.tag_configure("debug", foreground="#94A3B8")

    def append(self, text: str, level: str = "info"):
        """追加一行日志。"""
        self.text.configure(state=tk.NORMAL)
        self.text.insert(tk.END, f"{text}\n", level)
        self.text.see(tk.END)
        self.text.configure(state=tk.DISABLED)

    def clear(self):
        """清空日志。"""
        self.text.configure(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.configure(state=tk.DISABLED)
