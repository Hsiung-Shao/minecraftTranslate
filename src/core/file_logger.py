"""檔案記錄器：將翻譯過程的所有訊息寫入 log 檔案，方便事後檢查格式問題或錯誤。"""
from __future__ import annotations

import datetime
import threading
from pathlib import Path


class FileLogger:
    """Thread-safe file logger with separate warning/error log.

    主 log 記錄所有訊息；warnings.log 只記錄 warning/error 方便快速檢查問題。
    """

    def __init__(self, log_dir: Path, session_tag: str = "") -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = f"_{session_tag}" if session_tag else ""
        self.full_log_path = log_dir / f"translation_{timestamp}{tag}.log"
        self.issues_log_path = log_dir / f"issues_{timestamp}{tag}.log"

        self._lock = threading.Lock()
        self._full_fh = open(self.full_log_path, "w", encoding="utf-8")
        self._issues_fh = open(self.issues_log_path, "w", encoding="utf-8")

        self._write_header(self._full_fh, "完整翻譯記錄")
        self._write_header(self._issues_fh, "警告與錯誤")

        self._issue_count = 0

    def _write_header(self, fh, title: str) -> None:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fh.write(f"# {title}\n")
        fh.write(f"# 開始時間: {now}\n")
        fh.write("=" * 70 + "\n\n")
        fh.flush()

    def log(self, message: str, level: str = "info") -> None:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] [{level.upper()}] {message}\n"
        with self._lock:
            try:
                self._full_fh.write(line)
                self._full_fh.flush()
                if level in ("warning", "error"):
                    self._issues_fh.write(line)
                    self._issues_fh.flush()
                    self._issue_count += 1
            except (ValueError, OSError):
                pass

    def close(self) -> str:
        with self._lock:
            footer = (
                f"\n{'=' * 70}\n"
                f"# 結束時間: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"# 問題數: {self._issue_count}\n"
            )
            try:
                self._full_fh.write(footer)
                self._issues_fh.write(footer)
                self._full_fh.close()
                self._issues_fh.close()
            except (ValueError, OSError):
                pass
        return str(self.full_log_path)

    @property
    def issue_count(self) -> int:
        return self._issue_count
