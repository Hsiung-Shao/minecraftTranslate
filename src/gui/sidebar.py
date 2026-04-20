from __future__ import annotations

from pathlib import Path
from tkinter import filedialog
from typing import Callable

import customtkinter as ctk

from src.core.config import AppConfig
from src.core.models import LANGUAGES
from src.gui.theme import COLORS, FONTS


class SidebarPanel(ctk.CTkFrame):
    """Tabbed control panel.

    Three tabs keep the UI uncluttered:
      1. 翻譯  — mods folder, language, output, main action buttons
      2. 連線  — API provider selection
      3. 進階  — batch size / context / workers / VRAM detect
    """

    # (名稱, provider, url, 預設模型)
    API_PRESETS: list[tuple[str, str, str, str]] = [
        ("LM Studio (本機)", "local", "http://localhost:1234/v1", ""),
        ("Ollama (本機)", "local", "http://localhost:11434/v1", ""),
        ("Google Translate (免費)", "google", "", ""),
        ("自訂 (本機 OpenAI 相容)", "local", "", ""),
    ]

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
        super().__init__(parent, fg_color=COLORS["bg_panel"], width=340)
        self.config = config
        self._on_test_connection = on_test_connection
        self._on_analyze = on_analyze
        self._on_start = on_start
        self._on_select_mods = on_select_mods
        self._on_pause = on_pause
        self._on_cancel = on_cancel
        self._on_log = on_log or (lambda msg, lvl: None)

        self._build_header()
        self._build_tabs()
        self._build_progress()
        self._build_action_bar()

        if self.config.mods_folder:
            mods_path = Path(self.config.mods_folder)
            if mods_path.is_dir():
                self._auto_detect_resourcepacks(mods_path)

    # ─── Layout scaffolding ──────────────────────────────────────────

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent", height=60)
        header.pack(fill="x", padx=20, pady=(18, 8))

        ctk.CTkLabel(
            header,
            text="MC 翻譯工具",
            font=FONTS["display"],
            text_color=COLORS["text"],
            anchor="w",
        ).pack(anchor="w")
        ctk.CTkLabel(
            header,
            text="使用 AI 翻譯 Minecraft 模組",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
            anchor="w",
        ).pack(anchor="w")

    def _build_tabs(self) -> None:
        self.tabs = ctk.CTkTabview(
            self,
            fg_color=COLORS["bg_panel_2"],
            segmented_button_fg_color=COLORS["bg_panel"],
            segmented_button_selected_color=COLORS["accent"],
            segmented_button_selected_hover_color=COLORS["accent_hover"],
            segmented_button_unselected_color=COLORS["bg_panel"],
            segmented_button_unselected_hover_color=COLORS["bg_hover"],
            text_color=COLORS["text"],
        )
        self.tabs.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        self.tabs.add("翻譯")
        self.tabs.add("連線")
        self.tabs.add("進階")

        self._build_translate_tab(self.tabs.tab("翻譯"))
        self._build_connection_tab(self.tabs.tab("連線"))
        self._build_advanced_tab(self.tabs.tab("進階"))

    # ─── Tab 1: Translate (main flow) ────────────────────────────────

    def _build_translate_tab(self, parent) -> None:
        scroll = ctk.CTkScrollableFrame(
            parent, fg_color="transparent",
            scrollbar_button_color=COLORS["border"],
        )
        scroll.pack(fill="both", expand=True)

        # Mods folder card
        self._card_label(scroll, "MODS 資料夾")
        folder_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        folder_frame.pack(fill="x", padx=4, pady=(0, 4))
        self.folder_entry = self._entry(folder_frame)
        self.folder_entry.pack(side="left", fill="x", expand=True)
        if self.config.mods_folder:
            self.folder_entry.insert(0, self.config.mods_folder)
        self._icon_button(folder_frame, "📂", self._browse_folder).pack(side="right", padx=(6, 0))

        # Language
        self._card_label(scroll, "目標語言", pady_top=16)
        lang_names = [
            f"{lang.native_name} ({lang.code})" for lang in LANGUAGES.values()
        ]
        self.lang_var = ctk.StringVar()
        default_lang = LANGUAGES.get(self.config.target_language)
        if default_lang:
            self.lang_var.set(f"{default_lang.native_name} ({default_lang.code})")
        elif lang_names:
            self.lang_var.set(lang_names[0])
        ctk.CTkOptionMenu(
            scroll, variable=self.lang_var, values=lang_names,
            font=FONTS["body"],
            fg_color=COLORS["bg_input"], button_color=COLORS["border"],
            button_hover_color=COLORS["bg_hover"],
            dropdown_fg_color=COLORS["bg_panel_2"],
        ).pack(fill="x", padx=4, pady=(0, 4))

        # Output
        self._card_label(scroll, "輸出資料夾", pady_top=16)
        output_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        output_frame.pack(fill="x", padx=4, pady=(0, 4))
        self.output_entry = self._entry(output_frame)
        self.output_entry.pack(side="left", fill="x", expand=True)
        if self.config.output_folder:
            self.output_entry.insert(0, self.config.output_folder)
        self._icon_button(output_frame, "📂", self._browse_output).pack(side="right", padx=(6, 0))

        ctk.CTkLabel(
            scroll,
            text="自動偵測 Minecraft 的 resourcepacks 資料夾",
            font=FONTS["small"],
            text_color=COLORS["text_muted"],
        ).pack(anchor="w", padx=4, pady=(2, 0))

        # Pack name (less critical, keep compact)
        self._card_label(scroll, "資源包名稱", pady_top=16)
        self.pack_name_entry = self._entry(scroll)
        self.pack_name_entry.insert(0, self.config.resource_pack_name)
        self.pack_name_entry.pack(fill="x", padx=4, pady=(0, 4))

        # Hidden (kept for backward compat; pack_format is auto)
        self.pack_format_entry = ctk.CTkEntry(scroll)
        self.pack_format_entry.insert(0, str(self.config.pack_format))
        self.enable_log_var = ctk.BooleanVar(value=self.config.enable_file_log)

    # ─── Tab 2: Connection ───────────────────────────────────────────

    def _build_connection_tab(self, parent) -> None:
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        self._card_label(scroll, "翻譯服務商")
        preset_names = [p[0] for p in self.API_PRESETS]
        self._preset_var = ctk.StringVar(value=self._detect_preset())
        ctk.CTkOptionMenu(
            scroll, variable=self._preset_var,
            values=preset_names,
            font=FONTS["body"],
            fg_color=COLORS["bg_input"], button_color=COLORS["border"],
            button_hover_color=COLORS["bg_hover"],
            dropdown_fg_color=COLORS["bg_panel_2"],
            command=self._on_preset_change,
        ).pack(fill="x", padx=4, pady=(0, 4))

        self._url_label = ctk.CTkLabel(
            scroll, text="API 網址",
            font=FONTS["small"],
            text_color=COLORS["text_dim"],
        )
        self._url_label.pack(anchor="w", padx=4, pady=(14, 2))
        self.url_entry = self._entry(scroll)
        self.url_entry.insert(0, self.config.api_url)
        self.url_entry.pack(fill="x", padx=4, pady=(0, 4))

        # hidden api_key / model
        self.api_key_entry = ctk.CTkEntry(scroll)
        if self.config.api_key:
            self.api_key_entry.insert(0, self.config.api_key)
        self.model_var = ctk.StringVar(value=self.config.api_model or "自動")

        ctk.CTkButton(
            scroll, text="🔌  測試連線", font=FONTS["body_bold"],
            fg_color=COLORS["secondary"], hover_color=COLORS["secondary_hover"],
            text_color=COLORS["text"], height=36,
            command=self._on_test_connection,
        ).pack(fill="x", padx=4, pady=(14, 6))

        self.connection_status = ctk.CTkLabel(
            scroll, text="", font=FONTS["small"],
        )
        self.connection_status.pack(anchor="w", padx=4)

        # Tip card
        tip = ctk.CTkFrame(scroll, fg_color=COLORS["bg_panel"])
        tip.pack(fill="x", padx=4, pady=(20, 4))
        ctk.CTkLabel(
            tip, text="💡 提示",
            font=FONTS["body_bold"],
            text_color=COLORS["info"],
        ).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            tip,
            text=(
                "本機 LLM：開啟 LM Studio 載入模型，啟動 Server\n"
                "Google Translate：不需任何設定，點測試即可使用"
            ),
            font=FONTS["small"],
            text_color=COLORS["text_dim"],
            justify="left",
            wraplength=270,
        ).pack(anchor="w", padx=10, pady=(0, 10))

        self._update_url_visibility()

    # ─── Tab 3: Advanced ─────────────────────────────────────────────

    def _build_advanced_tab(self, parent) -> None:
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkButton(
            scroll, text="🎯  偵測 VRAM 自動設定", font=FONTS["body_bold"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            height=38, command=self._on_detect_vram,
        ).pack(fill="x", padx=4, pady=(4, 14))

        self._labeled_entry(scroll, "批次大小", "batch_size_entry",
                             str(self.config.batch_size))
        self._labeled_entry(scroll, "溫度 (0-2)", "temp_entry",
                             str(self.config.temperature))
        self._labeled_entry(scroll, "並行工作數", "workers_entry",
                             str(self.config.max_workers))
        self._labeled_entry(scroll, "Context 長度 (tokens)", "context_entry",
                             str(self.config.context_tokens))

        # Info card
        info = ctk.CTkFrame(scroll, fg_color=COLORS["bg_panel"])
        info.pack(fill="x", padx=4, pady=(20, 4))
        ctk.CTkLabel(
            info, text="📊 推薦設定",
            font=FONTS["body_bold"],
            text_color=COLORS["secondary"],
        ).pack(anchor="w", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            info,
            text=(
                "< 6 GB    → 8 / 4096 / 1\n"
                "6-12 GB   → 15 / 8192 / 2\n"
                "12-24 GB  → 20 / 16384 / 2\n"
                "> 24 GB   → 30 / 32768 / 3\n"
                "(批次 / context / workers)"
            ),
            font=FONTS["mono_sm"],
            text_color=COLORS["text_dim"],
            justify="left",
        ).pack(anchor="w", padx=10, pady=(0, 10))

    # ─── Progress + actions (always visible below tabs) ──────────────

    def _build_progress(self) -> None:
        box = ctk.CTkFrame(self, fg_color=COLORS["bg_panel_2"])
        box.pack(fill="x", padx=14, pady=(0, 8))

        ctk.CTkLabel(
            box, text="進度", font=FONTS["heading"],
            text_color=COLORS["text_dim"],
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self.progress_bar = ctk.CTkProgressBar(
            box, fg_color=COLORS["bg_input"],
            progress_color=COLORS["accent"],
            height=8,
        )
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 4))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(
            box, text="尚未開始", font=FONTS["small"],
            text_color=COLORS["text_dim"],
        )
        self.status_label.pack(anchor="w", padx=12)

        self.batch_progress_bar = ctk.CTkProgressBar(
            box, fg_color=COLORS["bg_input"],
            progress_color=COLORS["secondary"],
            height=6,
        )
        self.batch_progress_bar.pack(fill="x", padx=12, pady=(6, 2))
        self.batch_progress_bar.set(0)

        self.batch_status_label = ctk.CTkLabel(
            box, text="", font=FONTS["small"],
            text_color=COLORS["text_muted"],
        )
        self.batch_status_label.pack(anchor="w", padx=12)
        self.stats_label = ctk.CTkLabel(
            box, text="", font=FONTS["small"],
            text_color=COLORS["text_muted"],
        )
        self.stats_label.pack(anchor="w", padx=12, pady=(0, 10))

    def _build_action_bar(self) -> None:
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=(0, 14))

        # Primary: Start
        self.start_btn = ctk.CTkButton(
            bar, text="▶  開始翻譯", font=FONTS["body_bold"],
            fg_color=COLORS["accent"], hover_color=COLORS["accent_hover"],
            text_color=COLORS["text"], height=40,
            command=self._on_start,
        )
        self.start_btn.pack(fill="x", pady=(0, 6))

        # Secondary row
        sec = ctk.CTkFrame(bar, fg_color="transparent")
        sec.pack(fill="x", pady=(0, 6))
        self.analyze_btn = ctk.CTkButton(
            sec, text="🔍  分析", font=FONTS["body"],
            fg_color=COLORS["bg_panel_2"], hover_color=COLORS["bg_hover"],
            height=32, command=self._on_analyze,
        )
        self.analyze_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.select_btn = ctk.CTkButton(
            sec, text="✓  選擇模組", font=FONTS["body"],
            fg_color=COLORS["bg_panel_2"], hover_color=COLORS["bg_hover"],
            height=32, command=self._on_select_mods, state="disabled",
        )
        self.select_btn.pack(side="right", fill="x", expand=True, padx=(3, 0))

        # Pause / Cancel row
        ctrl = ctk.CTkFrame(bar, fg_color="transparent")
        ctrl.pack(fill="x")
        self.pause_btn = ctk.CTkButton(
            ctrl, text="⏸ 暫停", font=FONTS["small"],
            fg_color=COLORS["bg_panel_2"], hover_color=COLORS["bg_hover"],
            height=28, command=self._on_pause, state="disabled",
        )
        self.pause_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.cancel_btn = ctk.CTkButton(
            ctrl, text="✕ 取消", font=FONTS["small"],
            fg_color=COLORS["bg_panel_2"], hover_color=COLORS["error"],
            height=28, command=self._on_cancel, state="disabled",
        )
        self.cancel_btn.pack(side="right", fill="x", expand=True, padx=(3, 0))

    # ─── Reusable widget helpers ─────────────────────────────────────

    def _card_label(self, parent, text: str, pady_top: int = 8) -> None:
        ctk.CTkLabel(
            parent, text=text, font=FONTS["heading"],
            text_color=COLORS["text_dim"],
            anchor="w",
        ).pack(anchor="w", padx=4, pady=(pady_top, 4))

    def _entry(self, parent) -> ctk.CTkEntry:
        return ctk.CTkEntry(
            parent,
            font=FONTS["body"],
            fg_color=COLORS["bg_input"],
            border_color=COLORS["border"],
            text_color=COLORS["text"],
            height=32,
        )

    def _labeled_entry(self, parent, label: str, attr: str, default: str) -> None:
        ctk.CTkLabel(
            parent, text=label, font=FONTS["small"],
            text_color=COLORS["text_dim"],
            anchor="w",
        ).pack(anchor="w", padx=4, pady=(4, 2))
        entry = self._entry(parent)
        entry.insert(0, default)
        entry.pack(fill="x", padx=4, pady=(0, 4))
        setattr(self, attr, entry)

    def _icon_button(self, parent, text: str, command: Callable) -> ctk.CTkButton:
        return ctk.CTkButton(
            parent, text=text, width=36, height=32, font=FONTS["body"],
            fg_color=COLORS["bg_panel_2"], hover_color=COLORS["bg_hover"],
            command=command,
        )

    # ─── Preset / connection helpers ─────────────────────────────────

    def _detect_preset(self) -> str:
        provider = self.config.api_provider
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
            self._url_label.configure(text="API 網址 (Google Translate 不需填)")
            self.url_entry.configure(state="disabled")
        else:
            self._url_label.configure(text="API 網址")
            self.url_entry.configure(state="normal")

    def _get_selected_provider(self) -> str:
        preset = self._preset_var.get()
        provider, _, _ = self._get_preset_info(preset)
        return provider

    # ─── File dialogs ────────────────────────────────────────────────

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(title="選擇 mods 資料夾")
        if path:
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, path)
            self._auto_detect_resourcepacks(Path(path))

    def _auto_detect_resourcepacks(self, mods_folder) -> None:
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

    # ─── Config bundling ─────────────────────────────────────────────

    def get_selected_lang_code(self) -> str:
        text = self.lang_var.get()
        for lang in LANGUAGES.values():
            if f"{lang.native_name} ({lang.code})" == text:
                return lang.code
        return "zh_tw"

    def collect_config(self) -> AppConfig:
        def _int(entry, default):
            try:
                return int(entry.get())
            except ValueError:
                return default

        def _float(entry, default):
            try:
                return float(entry.get())
            except ValueError:
                return default

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
            pack_format=_int(self.pack_format_entry, 15),
            batch_size=max(1, _int(self.batch_size_entry, 10)),
            temperature=max(0.0, min(2.0, _float(self.temp_entry, 0.1))),
            max_retries=3,
            max_workers=max(1, min(8, _int(self.workers_entry, 2))),
            context_tokens=max(1024, _int(self.context_entry, 8192)),
            enable_file_log=bool(self.enable_log_var.get()),
        )

    # ─── VRAM detect ─────────────────────────────────────────────────

    def _on_detect_vram(self) -> None:
        from src.hardware.vram_detector import detect_gpu, recommend_settings

        self._on_log("正在偵測 GPU...", "info")
        info = detect_gpu()
        if not info:
            self._on_log("未偵測到 GPU，請手動設定", "warning")
            return

        self._on_log(f"偵測到 GPU: {info.name} ({info.vram_mb} MB)", "success")
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

    # ─── State updates called from app.py ────────────────────────────

    def set_running_state(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.start_btn.configure(state=state)
        self.analyze_btn.configure(state=state)
        self.select_btn.configure(state=state)
        self.url_entry.configure(state=state)
        self.api_key_entry.configure(state=state)
        self.folder_entry.configure(state=state)

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
            text=f"{mod_name} — 批次 {batch_current}/{batch_total}，"
                 f"字串 {strings_done}/{strings_total}"
        )
        self.stats_label.configure(
            text=f"快取命中 {cache_hits} │ API {strings_done - cache_hits}"
        )

    def reset_batch_progress(self) -> None:
        self.batch_progress_bar.set(0)
        self.batch_status_label.configure(text="")
        self.stats_label.configure(text="")

    def update_models(self, models: list[str]) -> None:
        pass  # Model dropdown removed

    def set_connection_status(self, connected: bool, message: str = "") -> None:
        if connected:
            self.connection_status.configure(
                text=f"● {message or '已連線'}",
                text_color=COLORS["success"],
            )
        else:
            self.connection_status.configure(
                text=f"● {message or '未連線'}",
                text_color=COLORS["error"],
            )
