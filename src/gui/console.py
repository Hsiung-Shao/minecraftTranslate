from __future__ import annotations

import datetime

import customtkinter as ctk

from src.gui.theme import COLORS, FONTS


class ConsolePanel(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass) -> None:
        super().__init__(parent, fg_color=COLORS["bg_dark"])

        header = ctk.CTkLabel(
            self, text="主控台輸出", font=FONTS["heading"],
            text_color=COLORS["text"],
        )
        header.pack(padx=10, pady=(10, 5), anchor="w")

        self.textbox = ctk.CTkTextbox(
            self,
            font=FONTS["mono"],
            fg_color=COLORS["bg_panel"],
            text_color=COLORS["text"],
            wrap="word",
            state="disabled",
        )
        self.textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.textbox.tag_config("info", foreground=COLORS["text"])
        self.textbox.tag_config("success", foreground=COLORS["success"])
        self.textbox.tag_config("warning", foreground=COLORS["warning"])
        self.textbox.tag_config("error", foreground=COLORS["error"])
        self.textbox.tag_config("timestamp", foreground=COLORS["text_dim"])

    def append(self, message: str, level: str = "info") -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.textbox.configure(state="normal")
        self.textbox.insert("end", f"[{timestamp}] ", "timestamp")
        self.textbox.insert("end", f"{message}\n", level)
        self.textbox.configure(state="disabled")
        self.textbox.see("end")

    def clear(self) -> None:
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
