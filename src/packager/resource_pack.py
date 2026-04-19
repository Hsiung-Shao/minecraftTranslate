from __future__ import annotations

import json
import zipfile
from pathlib import Path

from src.core.models import TargetLanguage


class ResourcePackBuilder:
    """Builds a Minecraft resource pack zip, preserving existing translations.

    If the target zip already exists, its contents are loaded first and new
    `add_lang_file()` calls merge (overriding entries only for the same
    namespace key). Namespaces not re-translated keep their existing content.
    """

    def __init__(
        self,
        output_path: Path,
        pack_name: str,
        pack_format: int,
        target_lang: TargetLanguage,
    ) -> None:
        self.output_path = output_path
        self.pack_name = pack_name
        self.pack_format = pack_format
        self.target_lang = target_lang
        # In-memory staging: path_in_zip -> bytes
        self._files: dict[str, bytes] = {}
        self._open = False

    def open(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        # Load existing zip contents if present
        if self.output_path.is_file():
            try:
                with zipfile.ZipFile(self.output_path, "r") as existing:
                    for name in existing.namelist():
                        # Skip pack.mcmeta — we re-generate it fresh
                        if name == "pack.mcmeta":
                            continue
                        try:
                            self._files[name] = existing.read(name)
                        except KeyError:
                            continue
            except zipfile.BadZipFile:
                # Corrupt zip — start fresh
                self._files = {}
        self._write_pack_mcmeta()
        self._open = True

    def _write_pack_mcmeta(self) -> None:
        mcmeta = {
            "pack": {
                "pack_format": self.pack_format,
                "description": (
                    f"{self.pack_name} - AI Translated "
                    f"({self.target_lang.native_name})"
                ),
            }
        }
        content = json.dumps(mcmeta, ensure_ascii=False, indent=2)
        self._files["pack.mcmeta"] = content.encode("utf-8")

    def add_lang_file(self, namespace: str, entries: dict[str, str]) -> None:
        if not self._open or not entries:
            return

        path = f"assets/{namespace}/lang/{self.target_lang.code}.json"
        sorted_entries = dict(sorted(entries.items()))
        content = json.dumps(sorted_entries, ensure_ascii=False, indent=2)
        self._files[path] = content.encode("utf-8")

    def close(self) -> None:
        if not self._open:
            return
        # Write to a temp file then replace, to avoid corrupting on crash
        tmp_path = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(self._files.keys()):
                zf.writestr(path, self._files[path])
        # Atomic replace
        tmp_path.replace(self.output_path)
        self._open = False

    def __enter__(self) -> ResourcePackBuilder:
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    @property
    def existing_namespaces(self) -> set[str]:
        """Return namespaces already present in this pack (pre-translation)."""
        import re
        pattern = re.compile(r"^assets/([^/]+)/lang/([a-z_]+)\.json$")
        result: set[str] = set()
        for path in self._files:
            m = pattern.match(path)
            if m and m.group(2) == self.target_lang.code:
                result.add(m.group(1))
        return result
