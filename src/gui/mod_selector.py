from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from src.core.models import ModInfo
from src.gui.theme import COLORS, FONTS


class ModSelectorDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        mods: list[ModInfo],
        on_confirm: Callable[[list[ModInfo]], None],
    ) -> None:
        super().__init__(parent)
        self.title("選擇要翻譯的模組")
        self.geometry("600x500")
        self.configure(fg_color=COLORS["bg_dark"])
        self.transient(parent)
        self.grab_set()

        self._mods = mods
        self._on_confirm = on_confirm
        self._checkboxes: list[tuple[ctk.BooleanVar, ModInfo]] = []

        self._build_ui()

    def _build_ui(self) -> None:
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=15, pady=(15, 5))

        ctk.CTkLabel(
            top_frame,
            text=f"共 {len(self._mods)} 個模組，請勾選要翻譯的項目:",
            font=FONTS["heading"],
            text_color=COLORS["text"],
        ).pack(side="left")

        btn_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        btn_frame.pack(side="right")

        ctk.CTkButton(
            btn_frame, text="全選", width=60, font=FONTS["small"],
            fg_color=COLORS["bg_input"], hover_color=COLORS["border"],
            command=self._select_all,
        ).pack(side="left", padx=(0, 5))

        ctk.CTkButton(
            btn_frame, text="取消全選", width=80, font=FONTS["small"],
            fg_color=COLORS["bg_input"], hover_color=COLORS["border"],
            command=self._deselect_all,
        ).pack(side="left")

        search_frame = ctk.CTkFrame(self, fg_color="transparent")
        search_frame.pack(fill="x", padx=15, pady=(5, 5))

        ctk.CTkLabel(
            search_frame, text="搜尋:", font=FONTS["body"],
            text_color=COLORS["text_dim"],
        ).pack(side="left")

        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", self._on_search)
        search_entry = ctk.CTkEntry(
            search_frame, textvariable=self._search_var,
            font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        search_entry.pack(side="left", fill="x", expand=True, padx=(5, 0))

        self._scroll_frame = ctk.CTkScrollableFrame(
            self, fg_color=COLORS["bg_panel"],
        )
        self._scroll_frame.pack(fill="both", expand=True, padx=15, pady=5)

        self._mod_widgets: list[tuple[ctk.CTkCheckBox, ctk.BooleanVar, ModInfo]] = []
        for mod in self._mods:
            var = ctk.BooleanVar(value=True)
            source = "JAR" if mod.jar_path.suffix == ".jar" else "資料夾"
            label = f"{mod.display_name}  ({mod.total_entries} 條) [{source}]"
            cb = ctk.CTkCheckBox(
                self._scroll_frame, text=label, variable=var,
                font=FONTS["body"], text_color=COLORS["text"],
                fg_color=COLORS["success"], hover_color=COLORS["accent"],
            )
            cb.pack(anchor="w", padx=10, pady=2)
            self._mod_widgets.append((cb, var, mod))

        bottom_frame = ctk.CTkFrame(self, fg_color="transparent")
        bottom_frame.pack(fill="x", padx=15, pady=(5, 15))

        self._count_label = ctk.CTkLabel(
            bottom_frame, text="", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        )
        self._count_label.pack(side="left")
        self._update_count()

        ctk.CTkButton(
            bottom_frame, text="取消", width=80, font=FONTS["body"],
            fg_color=COLORS["error"], hover_color=COLORS["accent_hover"],
            command=self.destroy,
        ).pack(side="right", padx=(5, 0))

        ctk.CTkButton(
            bottom_frame, text="開始翻譯選定模組", width=160, font=FONTS["body"],
            fg_color=COLORS["success"], hover_color="#3db88f",
            command=self._confirm,
        ).pack(side="right")

        for _, var, _ in self._mod_widgets:
            var.trace_add("write", lambda *a: self._update_count())

    def _select_all(self) -> None:
        for cb, var, _ in self._mod_widgets:
            if cb.winfo_ismapped():
                var.set(True)

    def _deselect_all(self) -> None:
        for _, var, _ in self._mod_widgets:
            var.set(False)

    def _on_search(self, *args) -> None:
        query = self._search_var.get().lower()
        for cb, var, mod in self._mod_widgets:
            if query in mod.display_name.lower() or query in mod.mod_id.lower():
                cb.pack(anchor="w", padx=10, pady=2)
            else:
                cb.pack_forget()

    def _update_count(self) -> None:
        selected = sum(1 for _, var, _ in self._mod_widgets if var.get())
        total_strings = sum(
            mod.total_entries for _, var, mod in self._mod_widgets if var.get()
        )
        self._count_label.configure(
            text=f"已選 {selected}/{len(self._mods)} 個模組，{total_strings} 條字串"
        )

    def _confirm(self) -> None:
        selected = [mod for _, var, mod in self._mod_widgets if var.get()]
        if not selected:
            return
        self.destroy()
        self._on_confirm(selected)
