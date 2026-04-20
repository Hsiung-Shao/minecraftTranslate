from __future__ import annotations

import sys
import threading
from pathlib import Path

import customtkinter as ctk

from src.core.config import AppConfig
from src.core.events import (
    BatchProgressEvent,
    ErrorEvent,
    EventBus,
    LogEvent,
    ProgressEvent,
    StateEvent,
)
from src.core.file_logger import FileLogger
from src.core.models import ModInfo, PipelineState
from src.gui.console import ConsolePanel
from src.gui.mod_selector import ModSelectorDialog
from src.gui.sidebar import SidebarPanel
from src.gui.theme import COLORS
from src.pipeline.pipeline import TranslationPipeline


CONFIG_PATH = Path("config.json")


def _resolve_icon_path() -> Path | None:
    """Return bundled icon.ico path, handling PyInstaller frozen layout."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent.parent
    candidate = base / "assets" / "icon.ico"
    return candidate if candidate.is_file() else None


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("Minecraft MOD 翻譯工具")
        self.geometry("1200x760")
        self.minsize(980, 620)
        self.configure(fg_color=COLORS["bg_dark"])

        icon_path = _resolve_icon_path()
        if icon_path:
            try:
                self.iconbitmap(str(icon_path))
            except Exception:
                pass

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.config = AppConfig.load(CONFIG_PATH)
        self.event_bus = EventBus()
        self.event_bus.set_tk_root(self)
        self.pipeline: TranslationPipeline | None = None
        self._worker: threading.Thread | None = None
        self._scanned_mods: list[ModInfo] = []
        self.file_logger: FileLogger | None = None

        self._setup_events()
        self._build_ui()

    def _setup_events(self) -> None:
        self.event_bus.subscribe("log", self._on_log)
        self.event_bus.subscribe("progress", self._on_progress)
        self.event_bus.subscribe("batch_progress", self._on_batch_progress)
        self.event_bus.subscribe("state_changed", self._on_state_changed)
        self.event_bus.subscribe("error", self._on_error)

    def _build_ui(self) -> None:
        main_frame = ctk.CTkFrame(self, fg_color="transparent")
        main_frame.pack(fill="both", expand=True)
        main_frame.grid_columnconfigure(1, weight=1)
        main_frame.grid_rowconfigure(0, weight=1)

        self.sidebar = SidebarPanel(
            main_frame,
            self.config,
            on_test_connection=self._test_connection,
            on_analyze=self._analyze,
            on_start=self._start_translation,
            on_select_mods=self._open_mod_selector,
            on_pause=self._pause_resume,
            on_cancel=self._cancel,
            on_log=lambda msg, lvl: self.console.append(msg, lvl),
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw", padx=(12, 6), pady=12)

        self.console = ConsolePanel(main_frame)
        self.console.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)

    def _test_connection(self) -> None:
        config = self.sidebar.collect_config()
        self.console.append("正在測試 API 連線...")

        def _test():
            from src.translator.engine import create_engine
            engine = create_engine(config)
            if engine.check_connection():
                models = engine.list_models()
                loaded = engine.get_loaded_model()
                self.after(0, lambda: self._on_connection_success(models, loaded))
            else:
                self.after(
                    0,
                    lambda: self._on_connection_fail("無法連線到 API"),
                )

        threading.Thread(target=_test, daemon=True).start()

    def _on_connection_success(self, models: list[str], loaded: str | None = None) -> None:
        self.sidebar.update_models(models)
        model_list = ", ".join(models) if models else "無"
        self.sidebar.set_connection_status(True, f"已連線 ({len(models)} 個模型)")
        self.console.append(f"連線成功！可用模型: {model_list}", "success")
        if loaded:
            self.console.append(f"當前已載入模型: {loaded}", "success")
        else:
            self.console.append(
                "警告: 目前沒有載入模型！若為本機請先在 LM Studio 載入模型。",
                "warning",
            )

    def _on_connection_fail(self, msg: str) -> None:
        self.sidebar.set_connection_status(False, msg)
        self.console.append(f"連線失敗: {msg}", "error")

    def _analyze(self) -> None:
        config = self.sidebar.collect_config()
        mods_folder = Path(config.mods_folder)

        if not mods_folder.is_dir():
            self.console.append("無效的 mods 資料夾路徑。", "error")
            return

        self.console.append(f"正在分析: {mods_folder}")

        target_lang = config.target_language

        def _run():
            pipeline = TranslationPipeline(config, self.event_bus)
            mods, skipped = pipeline.analyze(mods_folder, target_lang)
            total = sum(m.total_entries for m in mods)

            def _report():
                self._scanned_mods = mods
                jar_mods = [m for m in mods if m.jar_path.suffix == ".jar"]
                folder_mods = [m for m in mods if m.jar_path.suffix != ".jar"]
                self.console.append(
                    f"找到 {len(mods)} 個需翻譯的來源，共 {total} 條字串:",
                    "success",
                )
                if skipped:
                    self.console.append(
                        f"  已跳過 {len(skipped)} 個已有 {target_lang} 翻譯的模組",
                        "info",
                    )
                if jar_mods:
                    self.console.append(f"  --- JAR 模組 ({len(jar_mods)}) ---")
                    for mod in jar_mods:
                        namespaces = ", ".join(mod.namespaces.keys())
                        self.console.append(
                            f"  {mod.display_name}: {mod.total_entries} 條字串 "
                            f"[{namespaces}]"
                        )
                if folder_mods:
                    self.console.append(f"  --- 資料夾來源 ({len(folder_mods)}) ---")
                    for mod in folder_mods:
                        self.console.append(
                            f"  {mod.display_name}: {mod.total_entries} 條字串"
                        )
                self.console.append(
                    "點擊「開始翻譯」翻譯全部，或「選擇模組」挑選特定模組。",
                    "info",
                )
                self.sidebar.select_btn.configure(state="normal")

            self.after(0, _report)

        threading.Thread(target=_run, daemon=True).start()

    def _start_translation(self, selected_mods: list[ModInfo] | None = None) -> None:
        config = self.sidebar.collect_config()
        mods_folder = Path(config.mods_folder)

        if not mods_folder.is_dir():
            self.console.append("無效的 mods 資料夾路徑。", "error")
            return

        config.save(CONFIG_PATH)
        self.sidebar.set_running_state(True)
        self.console.clear()

        # Create log file for this session
        if config.enable_file_log:
            try:
                log_dir = Path(config.log_folder or "logs")
                tag = config.target_language
                self.file_logger = FileLogger(log_dir, tag)
                self.console.append(
                    f"記錄檔: {self.file_logger.full_log_path}", "info"
                )
            except Exception as e:
                self.console.append(f"建立記錄檔失敗: {e}", "warning")
                self.file_logger = None

        if selected_mods:
            self.console.append(
                f"開始翻譯選定的 {len(selected_mods)} 個模組...", "info"
            )
        else:
            self.console.append("開始翻譯全部模組...", "info")

        self.pipeline = TranslationPipeline(config, self.event_bus)

        def _run():
            result = self.pipeline.run(
                mods_folder, config.target_language,
                selected_mods=selected_mods,
            )
            if result:
                self.event_bus.publish_threadsafe(
                    "log", LogEvent(f"完成！輸出: {result}", "success")
                )

        self._worker = threading.Thread(target=_run, daemon=True)
        self._worker.start()

    def _open_mod_selector(self) -> None:
        if not self._scanned_mods:
            self.console.append("請先點擊「分析」掃描模組。", "warning")
            return
        ModSelectorDialog(self, self._scanned_mods, self._start_translation)

    def _pause_resume(self) -> None:
        if not self.pipeline:
            return
        tracker = self.pipeline.progress
        if tracker.state == PipelineState.RUNNING:
            tracker.pause()
            self.sidebar.pause_btn.configure(text="繼續")
            self.console.append("已暫停。", "warning")
        elif tracker.state == PipelineState.PAUSED:
            tracker.resume()
            self.sidebar.pause_btn.configure(text="暫停")
            self.console.append("已繼續。", "info")

    def _cancel(self) -> None:
        if self.pipeline:
            self.pipeline.progress.cancel()
            self.console.append("正在取消...", "warning")

    def _on_log(self, event: LogEvent) -> None:
        self.console.append(event.message, event.level)
        if self.file_logger is not None:
            self.file_logger.log(event.message, event.level)

    def _on_progress(self, event: ProgressEvent) -> None:
        if event.total > 0:
            value = event.current / event.total
            eta_min = int(event.eta_seconds // 60)
            eta_sec = int(event.eta_seconds % 60)
            status = (
                f"模組 {event.current}/{event.total} "
                f"| 預估剩餘: {eta_min}分{eta_sec}秒"
            )
            self.sidebar.update_progress(value, status)
            self.sidebar.reset_batch_progress()

    def _on_batch_progress(self, event: BatchProgressEvent) -> None:
        self.sidebar.update_batch_progress(
            event.mod_name,
            event.batch_current,
            event.batch_total,
            event.strings_done,
            event.strings_total,
            event.cache_hits,
        )

    def _on_state_changed(self, event: StateEvent) -> None:
        state = event.new_state
        if state in (
            PipelineState.COMPLETED.value,
            PipelineState.CANCELLED.value,
            PipelineState.ERROR.value,
        ):
            self.sidebar.set_running_state(False)
            self.sidebar.pause_btn.configure(text="暫停")
            if state == PipelineState.COMPLETED.value:
                self.sidebar.update_progress(1.0, "已完成！")
            elif state == PipelineState.CANCELLED.value:
                self.sidebar.update_progress(0, "已取消")

            if self.file_logger is not None:
                issue_count = self.file_logger.issue_count
                full_path = self.file_logger.full_log_path
                issues_path = self.file_logger.issues_log_path
                self.file_logger.close()
                self.console.append(
                    f"記錄檔已儲存: {full_path}", "info"
                )
                if issue_count > 0:
                    self.console.append(
                        f"共 {issue_count} 個警告/錯誤，已存至: {issues_path}",
                        "warning",
                    )
                self.file_logger = None

    def _on_error(self, event: ErrorEvent) -> None:
        self.console.append(
            f"錯誤 ({event.context}): {event.exception}", "error"
        )
        if self.file_logger is not None:
            self.file_logger.log(
                f"錯誤 ({event.context}): {event.exception}", "error"
            )


def run_app() -> None:
    app = App()
    app.mainloop()
