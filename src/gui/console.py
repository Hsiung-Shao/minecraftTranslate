from __future__ import annotations

import datetime

import customtkinter as ctk

from src.gui.theme import COLORS, FONTS


class ConsolePanel(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkBaseClass) -> None:
        super().__init__(parent, fg_color=COLORS["bg_panel"])

        header = ctk.CTkFrame(self, fg_color="transparent", height=50)
        header.pack(fill="x", padx=16, pady=(14, 4))

        ctk.CTkLabel(
            header,
            text="主控台",
            font=FONTS["title"],
            text_color=COLORS["text"],
        ).pack(side="left")

        self._clear_btn = ctk.CTkButton(
            header, text="清除", width=60, height=28,
            font=FONTS["small"],
            fg_color=COLORS["bg_panel_2"], hover_color=COLORS["bg_hover"],
            command=self.clear,
        )
        self._clear_btn.pack(side="right")

        self.textbox = ctk.CTkTextbox(
            self,
            font=FONTS["mono"],
            fg_color=COLORS["bg_input"],
            text_color=COLORS["text"],
            border_color=COLORS["border_subtle"],
            border_width=1,
            wrap="word",
            state="disabled",
            corner_radius=6,
        )
        self.textbox.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self.textbox.tag_config("info", foreground=COLORS["text"])
        self.textbox.tag_config("success", foreground=COLORS["success"])
        self.textbox.tag_config("warning", foreground=COLORS["warning"])
        self.textbox.tag_config("error", foreground=COLORS["error"])
        self.textbox.tag_config("timestamp", foreground=COLORS["text_muted"])

    def append(self, message: str, level: str = "info") -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.textbox.configure(state="normal")
        self.textbox.insert("end", f"{timestamp}  ", "timestamp")
        self.textbox.insert("end", f"{message}\n", level)
        self.textbox.configure(state="disabled")
        self.textbox.see("end")

    def clear(self) -> None:
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", "end")
        self.textbox.configure(state="disabled")
