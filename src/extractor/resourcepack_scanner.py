"""掃描 resourcepacks 資料夾中的 zip，讀取已有翻譯。

舊版只回傳 namespace 集合，現在也回傳完整的 {namespace: {key: text}} 映射，
讓 scanner 能做逐鍵比對（只翻譯缺少的項目），而非整個模組跳過。
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path


class ResourcePackScanner:
    LANG_PATTERN = re.compile(r"^assets/([^/]+)/lang/([a-z_]+)\.json$")

    def scan(self, resourcepacks_dir: Path, target_lang: str) -> set[str]:
        """Backward-compatible: return set of namespaces with target_lang translation."""
        return set(self.load_translations(resourcepacks_dir, target_lang).keys())

    def load_translations(
        self, resourcepacks_dir: Path, target_lang: str
    ) -> dict[str, dict[str, str]]:
        """Return {namespace: {key: translated_text}} merged from all zips.

        When multiple zips translate the same namespace, later-loaded packs
        override earlier ones (matching Minecraft's override order).
        """
        result: dict[str, dict[str, str]] = {}

        if not resourcepacks_dir.is_dir():
            return result

        for zip_path in sorted(resourcepacks_dir.glob("*.zip")):
            try:
                self._load_from_zip(zip_path, target_lang, result)
            except (zipfile.BadZipFile, OSError):
                continue

        return result

    def _load_from_zip(
        self, zip_path: Path, target_lang: str, result: dict[str, dict[str, str]]
    ) -> None:
        with zipfile.ZipFile(zip_path, "r") as zf:
            for name in zf.namelist():
                m = self.LANG_PATTERN.match(name)
                if not m or m.group(2) != target_lang:
                    continue
                namespace = m.group(1)
                try:
                    raw = zf.read(name).decode("utf-8", errors="replace")
                    data = json.loads(raw)
                    if isinstance(data, dict):
                        ns_dict = result.setdefault(namespace, {})
                        for k, v in data.items():
                            if isinstance(v, str) and v.strip():
                                ns_dict[str(k)] = v
                except (json.JSONDecodeError, KeyError):
                    continue
