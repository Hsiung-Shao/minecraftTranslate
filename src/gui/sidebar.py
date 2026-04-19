from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from src.core.config import AppConfig
from src.core.models import LANGUAGES
from src.gui.theme import COLORS, FONTS


class SidebarPanel(ctk.CTkScrollableFrame):
    def __init__(
        self,
        parent: ctk.CTkBaseClass,
        config: AppConfig,
        on_test_connection: Callable,
        on_analyze: Callable,
        on_start: Callable,
        on_select_mods: Callable,
        on_pause: Callable,
        on_cancel: Callable,
        on_log: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(
            parent, fg_color=COLORS["bg_panel"], width=320,
        )
        self.config = config
        self._on_test_connection = on_test_connection
        self._on_analyze = on_analyze
        self._on_start = on_start
        self._on_select_mods = on_select_mods
        self._on_pause = on_pause
        self._on_cancel = on_cancel
        self._on_log = on_log or (lambda msg, lvl: None)

        self._build_connection_section()
        self._build_source_section()
        self._build_language_section()
        self._build_output_section()
        self._build_settings_section()
        self._build_progress_section()
        self._build_action_buttons()

        # Auto-fill output folder on startup if mods_folder is already set
        from pathlib import Path
        if self.config.mods_folder:
            mods_path = Path(self.config.mods_folder)
            if mods_path.is_dir():
                self._auto_detect_resourcepacks(mods_path)

    def _make_section_label(self, text: str) -> None:
        ctk.CTkLabel(
            self, text=text, font=FONTS["heading"],
            text_color=COLORS["accent"],
        ).pack(padx=15, pady=(15, 5), anchor="w")
        ctk.CTkFrame(
            self, height=1, fg_color=COLORS["border"],
        ).pack(fill="x", padx=15, pady=(0, 8))

    # (名稱, provider, url, 預設模型)
    API_PRESETS: list[tuple[str, str, str, str]] = [
        ("LM Studio (本機)", "local", "http://localhost:1234/v1", ""),
        ("Ollama (本機)", "local", "http://localhost:11434/v1", ""),
        ("Google Translate (免費)", "google", "", ""),
        ("自訂 (本機 OpenAI 相容)", "local", "", ""),
    ]

    def _build_connection_section(self) -> None:
        self._make_section_label("API 連線設定")

        ctk.CTkLabel(
            self, text="服務商:", font=FONTS["body"],
            text_color=COLORS["text_dim"],
        ).pack(padx=15, anchor="w")

        preset_names = [p[0] for p in self.API_PRESETS]
        self._preset_var = ctk.StringVar(value=self._detect_preset())
        preset_menu = ctk.CTkOptionMenu(
            self, variable=self._preset_var,
            values=preset_names,
            font=FONTS["body"], fg_color=COLORS["bg_input"],
            command=self._on_preset_change,
        )
        preset_menu.pack(fill="x", padx=15, pady=(2, 5))

        self._url_label = ctk.CTkLabel(
            self, text="API 網址:", font=FONTS["body"],
            text_color=COLORS["text_dim"],
        )
        self._url_label.pack(padx=15, anchor="w")
        self.url_entry = ctk.CTkEntry(
            self, font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        self.url_entry.insert(0, self.config.api_url)
        self.url_entry.pack(fill="x", padx=15, pady=(2, 5))

        # Hidden fields kept for backward compat
        self.api_key_entry = ctk.CTkEntry(
            self, font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        if self.config.api_key:
            self.api_key_entry.insert(0, self.config.api_key)
        self.model_var = ctk.StringVar(value=self.config.api_model or "自動")

        self.test_btn = ctk.CTkButton(
            self, text="測試連線", font=FONTS["body"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._on_test_connection,
        )
        self.test_btn.pack(fill="x", padx=15, pady=(2, 8))

        self.connection_status = ctk.CTkLabel(
            self, text="", font=FONTS["small"],
        )
        self.connection_status.pack(padx=15, anchor="w")

        self._update_url_visibility()

    def _detect_preset(self) -> str:
        provider = self.config.api_provider
        # Handle legacy config values
        if provider == "openai_compat":
            provider = "local"
        url = self.config.api_url
        for name, p, u, _ in self.API_PRESETS:
            if p == provider and (u == url or not u):
                return name
        return "自訂 (本機 OpenAI 相容)"

    def _get_preset_info(self, name: str) -> tuple[str, str, str]:
        for pname, provider, url, model in self.API_PRESETS:
            if pname == name:
                return provider, url, model
        return "local", "", ""

    def _on_preset_change(self, choice: str) -> None:
        provider, url, model = self._get_preset_info(choice)
        if url:
            self.url_entry.delete(0, "end")
            self.url_entry.insert(0, url)
        if model:
            self.model_var.set(model)
        self._update_url_visibility()

    def _update_url_visibility(self) -> None:
        preset = self._preset_var.get()
        provider, _, _ = self._get_preset_info(preset)
        if provider == "google":
            self._url_label.configure(text="（Google Translate 不需 URL）")
            self.url_entry.configure(state="disabled")
        else:
            self._url_label.configure(text="API 網址:")
            self.url_entry.configure(state="normal")

    def _get_selected_provider(self) -> str:
        preset = self._preset_var.get()
        provider, _, _ = self._get_preset_info(preset)
        return provider

    def _build_source_section(self) -> None:
        self._make_section_label("Mods 資料夾")

        folder_frame = ctk.CTkFrame(self, fg_color="transparent")
        folder_frame.pack(fill="x", padx=15, pady=(2, 5))

        self.folder_entry = ctk.CTkEntry(
            folder_frame, font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        self.folder_entry.pack(side="left", fill="x", expand=True)
        if self.config.mods_folder:
            self.folder_entry.insert(0, self.config.mods_folder)

        ctk.CTkButton(
            folder_frame, text="...", width=40, font=FONTS["body"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._browse_folder,
        ).pack(side="right", padx=(5, 0))

    def _build_language_section(self) -> None:
        self._make_section_label("目標語言")

        lang_names = [
            f"{lang.native_name} ({lang.code})" for lang in LANGUAGES.values()
        ]
        self.lang_var = ctk.StringVar()

        default_lang = LANGUAGES.get(self.config.target_language)
        if default_lang:
            self.lang_var.set(f"{default_lang.native_name} ({default_lang.code})")
        elif lang_names:
            self.lang_var.set(lang_names[0])

        self.lang_dropdown = ctk.CTkOptionMenu(
            self, variable=self.lang_var, values=lang_names,
            font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        self.lang_dropdown.pack(fill="x", padx=15, pady=(2, 5))

    def _build_output_section(self) -> None:
        self._make_section_label("輸出設定")

        ctk.CTkLabel(
            self, text="資源包名稱:", font=FONTS["body"],
            text_color=COLORS["text_dim"],
        ).pack(padx=15, anchor="w")
        self.pack_name_entry = ctk.CTkEntry(
            self, font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        self.pack_name_entry.insert(0, self.config.resource_pack_name)
        self.pack_name_entry.pack(fill="x", padx=15, pady=(2, 5))

        # Hidden: pack_format is auto-detected from game dir during scan.
        self.pack_format_entry = ctk.CTkEntry(
            self, font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        self.pack_format_entry.insert(0, str(self.config.pack_format))

        ctk.CTkLabel(
            self, text="輸出資料夾:", font=FONTS["body"],
            text_color=COLORS["text_dim"],
        ).pack(padx=15, anchor="w")

        output_frame = ctk.CTkFrame(self, fg_color="transparent")
        output_frame.pack(fill="x", padx=15, pady=(2, 5))

        self.output_entry = ctk.CTkEntry(
            output_frame, font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        self.output_entry.pack(side="left", fill="x", expand=True)
        if self.config.output_folder:
            self.output_entry.insert(0, self.config.output_folder)

        ctk.CTkButton(
            output_frame, text="...", width=40, font=FONTS["body"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            command=self._browse_output,
        ).pack(side="right", padx=(5, 0))

        # Log output is always enabled but UI controls are hidden
        self.enable_log_var = ctk.BooleanVar(value=self.config.enable_file_log)

    def _build_settings_section(self) -> None:
        self._make_section_label("翻譯設定")

        ctk.CTkLabel(
            self, text="批次大小:", font=FONTS["body"],
            text_color=COLORS["text_dim"],
        ).pack(padx=15, anchor="w")
        self.batch_size_entry = ctk.CTkEntry(
            self, font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        self.batch_size_entry.insert(0, str(self.config.batch_size))
        self.batch_size_entry.pack(fill="x", padx=15, pady=(2, 5))

        ctk.CTkLabel(
            self, text="溫度:", font=FONTS["body"],
            text_color=COLORS["text_dim"],
        ).pack(padx=15, anchor="w")
        self.temp_entry = ctk.CTkEntry(
            self, font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        self.temp_entry.insert(0, str(self.config.temperature))
        self.temp_entry.pack(fill="x", padx=15, pady=(2, 5))

        ctk.CTkLabel(
            self, text="並行工作數:", font=FONTS["body"],
            text_color=COLORS["text_dim"],
        ).pack(padx=15, anchor="w")
        self.workers_entry = ctk.CTkEntry(
            self, font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        self.workers_entry.insert(0, str(self.config.max_workers))
        self.workers_entry.pack(fill="x", padx=15, pady=(2, 5))

        ctk.CTkLabel(
            self, text="Context 長度 (tokens):", font=FONTS["body"],
            text_color=COLORS["text_dim"],
        ).pack(padx=15, anchor="w")
        self.context_entry = ctk.CTkEntry(
            self, font=FONTS["body"], fg_color=COLORS["bg_input"],
        )
        self.context_entry.insert(0, str(self.config.context_tokens))
        self.context_entry.pack(fill="x", padx=15, pady=(2, 5))

        self.detect_vram_btn = ctk.CTkButton(
            self, text="偵測 VRAM 自動設定", font=FONTS["body"],
            fg_color=COLORS["info"], hover_color="#5ba8c3",
            command=self._on_detect_vram,
        )
        self.detect_vram_btn.pack(fill="x", padx=15, pady=(5, 5))

    def _build_progress_section(self) -> None:
        self._make_section_label("翻譯進度")

        ctk.CTkLabel(
            self, text="總進度 (模組):", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        ).pack(padx=15, anchor="w")

        self.progress_bar = ctk.CTkProgressBar(
            self, fg_color=COLORS["bg_input"],
            progress_color=COLORS["success"],
        )
        self.progress_bar.pack(fill="x", padx=15, pady=(2, 2))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            self, text="就緒", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        )
        self.status_label.pack(padx=15, anchor="w")

        ctk.CTkLabel(
            self, text="目前模組進度 (批次):", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        ).pack(padx=15, pady=(8, 0), anchor="w")

        self.batch_progress_bar = ctk.CTkProgressBar(
            self, fg_color=COLORS["bg_input"],
            progress_color=COLORS["info"],
        )
        self.batch_progress_bar.pack(fill="x", padx=15, pady=(2, 2))
        self.batch_progress_bar.set(0)

        self.batch_status_label = ctk.CTkLabel(
            self, text="", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        )
        self.batch_status_label.pack(padx=15, anchor="w")

        self.stats_label = ctk.CTkLabel(
            self, text="", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        )
        self.stats_label.pack(padx=15, pady=(4, 0), anchor="w")

    def _build_action_buttons(self) -> None:
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=15, pady=(10, 5))

        self.analyze_btn = ctk.CTkButton(
            btn_frame, text="分析", font=FONTS["body"],
            fg_color=COLORS["bg_input"], hover_color=COLORS["border"],
            command=self._on_analyze,
        )
        self.analyze_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.select_btn = ctk.CTkButton(
            btn_frame, text="選擇模組", font=FONTS["body"],
            fg_color=COLORS["info"], hover_color="#5ba8c3",
            command=self._on_select_mods, state="disabled",
        )
        self.select_btn.pack(side="left", expand=True, fill="x", padx=(5, 0))

        start_frame = ctk.CTkFrame(self, fg_color="transparent")
        start_frame.pack(fill="x", padx=15, pady=(5, 5))

        self.start_btn = ctk.CTkButton(
            start_frame, text="翻譯全部", font=FONTS["body"],
            fg_color=COLORS["success"], hover_color="#3db88f",
            command=self._on_start,
        )
        self.start_btn.pack(fill="x")

        ctrl_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctrl_frame.pack(fill="x", padx=15, pady=(5, 15))

        self.pause_btn = ctk.CTkButton(
            ctrl_frame, text="暫停", font=FONTS["body"],
            fg_color=COLORS["warning"], hover_color="#d99400",
            command=self._on_pause, state="disabled",
        )
        self.pause_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))

        self.cancel_btn = ctk.CTkButton(
            ctrl_frame, text="取消", font=FONTS["body"],
            fg_color=COLORS["error"], hover_color=COLORS["accent_hover"],
            command=self._on_cancel, state="disabled",
        )
        self.cancel_btn.pack(side="left", expand=True, fill="x", padx=(5, 0))

    def _browse_folder(self) -> None:
        from pathlib import Path
        path = filedialog.askdirectory(title="選擇 mods 資料夾")
        if path:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, path)
            self._auto_detect_resourcepacks(Path(path))

    def _auto_detect_resourcepacks(self, mods_folder) -> None:
        """Detect the Minecraft resourcepacks folder from the mods folder path
        and auto-fill the output folder if it's empty or still a default.
        """
        from pathlib import Path
        rp_dir: Path | None = None
        if mods_folder.name == "mods":
            candidate = mods_folder.parent / "resourcepacks"
            if candidate.is_dir():
                rp_dir = candidate
        if rp_dir is None:
            candidate = mods_folder / "resourcepacks"
            if candidate.is_dir():
                rp_dir = candidate

        if rp_dir:
            current = self.output_entry.get().strip()
            # Only overwrite if empty or pointing to non-existent path
            if not current or not Path(current).is_dir():
                self.output_entry.delete(0, "end")
                self.output_entry.insert(0, str(rp_dir))
                self._on_log(
                    f"已自動設定輸出資料夾為遊戲的 resourcepacks: {rp_dir}",
                    "info",
                )

    def _browse_output(self) -> None:
        path = filedialog.askdirectory(title="選擇輸出資料夾")
        if path:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, path)

    def _open_log_folder(self) -> None:
        import os
        import subprocess
        import sys
        from pathlib import Path
        log_dir = Path(self.config.log_folder or "logs").resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(str(log_dir))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(log_dir)])
            else:
                subprocess.Popen(["xdg-open", str(log_dir)])
        except Exception as e:
            self._on_log(f"無法開啟資料夾: {e}", "error")

    def get_selected_lang_code(self) -> str:
        text = self.lang_var.get()
        for lang in LANGUAGES.values():
            if f"{lang.native_name} ({lang.code})" == text:
                return lang.code
        return "zh_tw"

    def collect_config(self) -> AppConfig:
        try:
            batch_size = int(self.batch_size_entry.get())
        except ValueError:
            batch_size = 10
        try:
            temperature = float(self.temp_entry.get())
        except ValueError:
            temperature = 0.1
        try:
            pack_format = int(self.pack_format_entry.get())
        except ValueError:
            pack_format = 15

        try:
            max_workers = int(self.workers_entry.get())
        except ValueError:
            max_workers = 2

        try:
            context_tokens = int(self.context_entry.get())
        except ValueError:
            context_tokens = 8192

        enable_file_log = bool(self.enable_log_var.get())

        model = self.model_var.get()
        if model in ("auto", "自動"):
            model = ""

        return AppConfig(
            api_provider=self._get_selected_provider(),
            api_url=self.url_entry.get().strip(),
            api_key=self.api_key_entry.get().strip(),
            api_model=model,
            target_language=self.get_selected_lang_code(),
            mods_folder=self.folder_entry.get().strip(),
            output_folder=self.output_entry.get().strip(),
            resource_pack_name=self.pack_name_entry.get().strip() or "ModTranslation",
            pack_format=pack_format,
            batch_size=max(1, batch_size),
            temperature=max(0.0, min(2.0, temperature)),
            max_retries=3,
            max_workers=max(1, min(8, max_workers)),
            context_tokens=max(1024, context_tokens),
            enable_file_log=enable_file_log,
        )

    def _on_detect_vram(self) -> None:
        from src.hardware.vram_detector import detect_gpu, recommend_settings

        self._on_log("正在偵測 GPU...", "info")
        info = detect_gpu()
        if not info:
            self._on_log("未偵測到 GPU，請手動設定", "warning")
            return

        self._on_log(
            f"偵測到 GPU: {info.name} ({info.vram_mb} MB)", "success"
        )
        rec = recommend_settings(info.vram_mb)
        self._on_log(rec.model_hint, "info")
        self._on_log(
            f"建議設定: context={rec.context_tokens}, "
            f"batch_size={rec.batch_size}, 並行={rec.max_workers}",
            "info",
        )

        self.context_entry.delete(0, "end")
        self.context_entry.insert(0, str(rec.context_tokens))
        self.batch_size_entry.delete(0, "end")
        self.batch_size_entry.insert(0, str(rec.batch_size))
        self.workers_entry.delete(0, "end")
        self.workers_entry.insert(0, str(rec.max_workers))
        self._on_log("已自動套用，可手動微調", "success")

    def set_running_state(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.start_btn.configure(state=state)
        self.analyze_btn.configure(state=state)
        self.select_btn.configure(state=state)
        self.url_entry.configure(state=state)
        self.api_key_entry.configure(state=state)
        self.folder_entry.configure(state=state)
        self.test_btn.configure(state=state)

        ctrl_state = "normal" if running else "disabled"
        self.pause_btn.configure(state=ctrl_state)
        self.cancel_btn.configure(state=ctrl_state)

    def update_progress(self, value: float, status: str) -> None:
        self.progress_bar.set(value)
        self.status_label.configure(text=status)

    def update_batch_progress(
        self, mod_name: str, batch_current: int, batch_total: int,
        strings_done: int, strings_total: int, cache_hits: int,
    ) -> None:
        if batch_total > 0:
            self.batch_progress_bar.set(batch_current / batch_total)
        self.batch_status_label.configure(
            text=f"{mod_name}: 批次 {batch_current}/{batch_total}，"
                 f"字串 {strings_done}/{strings_total}"
        )
        self.stats_label.configure(
            text=f"快取命中: {cache_hits} | "
                 f"API 翻譯: {strings_done - cache_hits}"
        )

    def reset_batch_progress(self) -> None:
        self.batch_progress_bar.set(0)
        self.batch_status_label.configure(text="")
        self.stats_label.configure(text="")

    def update_models(self, models: list[str]) -> None:
        values = ["自動"] + models
        self.model_dropdown.configure(values=values)

    def set_connection_status(self, connected: bool, message: str = "") -> None:
        if connected:
            self.connection_status.configure(
                text=message or "已連線",
                text_color=COLORS["success"],
            )
        else:
            self.connection_status.configure(
                text=message or "未連線",
                text_color=COLORS["error"],
            )
