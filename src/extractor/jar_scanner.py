from __future__ import annotations

import re
import zipfile
from pathlib import Path

from src.core.models import ModInfo
from src.extractor.lang_parser import LangParser


class JarScanner:
    LANG_PATTERN = re.compile(r"^assets/([^/]+)/lang/en_us\.json$")
    TARGET_LANG_PATTERN_TPL = "assets/{namespace}/lang/{lang}.json"

    def __init__(self) -> None:
        self._parser = LangParser()

    def scan_folder(
        self,
        mods_folder: Path,
        target_lang: str = "",
        external_translations: dict[str, dict[str, str]] | None = None,
    ) -> tuple[list[ModInfo], list[str]]:
        """Return (mods_needing_translation, fully_translated_display_names).

        A mod is only "skipped" (returned in second list) if ALL its keys
        are already translated — either in its own JAR or in external packs.
        Mods with partial translations are returned with existing_translations
        pre-filled, so BatchProcessor only translates missing keys.
        """
        mods: list[ModInfo] = []
        fully_translated: list[str] = []
        jar_files = sorted(mods_folder.glob("*.jar"))
        external = external_translations or {}

        for jar_path in jar_files:
            try:
                mod = self._scan_jar(jar_path, target_lang, external)
                if not mod or mod.total_entries == 0:
                    continue
                if mod.untranslated_count == 0:
                    fully_translated.append(mod.display_name)
                else:
                    mods.append(mod)
            except (zipfile.BadZipFile, OSError):
                continue

        return mods, fully_translated

    def _scan_jar(
        self,
        jar_path: Path,
        target_lang: str,
        external: dict[str, dict[str, str]],
    ) -> ModInfo | None:
        namespaces: dict[str, dict[str, str]] = {}
        existing: dict[str, dict[str, str]] = {}

        with zipfile.ZipFile(jar_path, "r") as jar:
            jar_names = set(jar.namelist())

            for entry_name in jar_names:
                match = self.LANG_PATTERN.match(entry_name)
                if not match:
                    continue
                namespace = match.group(1)
                try:
                    raw = jar.read(entry_name)
                    entries = self._parser.parse(raw)
                    if entries:
                        namespaces[namespace] = entries
                except Exception:
                    continue

            if not target_lang or not namespaces:
                return self._make_mod_info(jar_path, namespaces, {})

            # Collect existing translations for each namespace
            for ns in namespaces:
                merged: dict[str, str] = {}
                # 1) From the JAR itself (mod's bundled translation)
                target_path = self.TARGET_LANG_PATTERN_TPL.format(
                    namespace=ns, lang=target_lang
                )
                if target_path in jar_names:
                    try:
                        raw = jar.read(target_path)
                        parsed = self._parser.parse(raw)
                        if parsed:
                            merged.update(parsed)
                    except Exception:
                        pass
                # 2) From external resource packs (overrides bundled)
                if ns in external:
                    merged.update(external[ns])
                if merged:
                    existing[ns] = merged

        return self._make_mod_info(jar_path, namespaces, existing)

    def _make_mod_info(
        self,
        jar_path: Path,
        namespaces: dict[str, dict[str, str]],
        existing: dict[str, dict[str, str]],
    ) -> ModInfo | None:
        if not namespaces:
            return None
        mod_id = self._extract_mod_id(jar_path, namespaces)
        return ModInfo(
            mod_id=mod_id,
            display_name=self._make_display_name(mod_id),
            jar_path=jar_path,
            namespaces=namespaces,
            existing_translations=existing,
        )

    def _extract_mod_id(
        self, jar_path: Path, namespaces: dict[str, dict[str, str]]
    ) -> str:
        if len(namespaces) == 1:
            return next(iter(namespaces))
        return jar_path.stem.split("-")[0].lower()

    def _make_display_name(self, mod_id: str) -> str:
        return mod_id.replace("_", " ").replace("-", " ").title()
