from __future__ import annotations

from pathlib import Path

from src.core.models import ModInfo
from src.extractor.lang_parser import LangParser
from src.extractor.snbt_parser import SnbtParser


class FolderScanner:
    LANG_FILENAME_JSON = "en_us.json"
    LANG_FILENAME_SNBT = "en_us.snbt"

    KNOWN_SCAN_DIRS = [
        "config",
        "kubejs",
        "patchouli_books",
        "local",
        "scripts",
        "defaultconfigs",
    ]

    def __init__(self) -> None:
        self._json_parser = LangParser()
        self._snbt_parser = SnbtParser()

    def scan_game_dir(
        self,
        game_dir: Path,
        target_lang: str = "",
        external_translations: dict[str, dict[str, str]] | None = None,
    ) -> tuple[list[ModInfo], list[str]]:
        mods: list[ModInfo] = []
        fully_translated: list[str] = []
        seen_files: set[Path] = set()
        external = external_translations or {}

        for subdir_name in self.KNOWN_SCAN_DIRS:
            subdir = game_dir / subdir_name
            if subdir.is_dir():
                self._scan_recursive(
                    subdir, game_dir, target_lang, mods, fully_translated,
                    seen_files, external,
                )

        for lang_file in game_dir.glob(f"**/lang/{self.LANG_FILENAME_JSON}"):
            if lang_file.resolve() not in seen_files:
                rel = lang_file.relative_to(game_dir)
                if not str(rel).startswith("mods"):
                    self._process_lang_file(
                        lang_file, game_dir, target_lang, mods, fully_translated,
                        seen_files, external,
                    )

        return mods, fully_translated

    def _scan_recursive(
        self,
        directory: Path,
        base_dir: Path,
        target_lang: str,
        mods: list[ModInfo],
        fully_translated: list[str],
        seen_files: set[Path],
        external: dict[str, dict[str, str]],
    ) -> None:
        for filename in (self.LANG_FILENAME_JSON, self.LANG_FILENAME_SNBT):
            for lang_file in directory.rglob(filename):
                if lang_file.parent.name == "lang":
                    self._process_lang_file(
                        lang_file, base_dir, target_lang, mods, fully_translated,
                        seen_files, external,
                    )

    def _process_lang_file(
        self,
        lang_file: Path,
        base_dir: Path,
        target_lang: str,
        mods: list[ModInfo],
        fully_translated: list[str],
        seen_files: set[Path],
        external: dict[str, dict[str, str]] | None = None,
    ) -> None:
        resolved = lang_file.resolve()
        if resolved in seen_files:
            return
        seen_files.add(resolved)

        is_snbt = lang_file.suffix == ".snbt"

        try:
            raw = lang_file.read_bytes()
            if is_snbt:
                entries, array_keys = self._snbt_parser.parse(raw)
            else:
                entries = self._json_parser.parse(raw)
                array_keys = set()
        except Exception:
            return

        if not entries:
            return

        namespace = self._detect_namespace(lang_file, base_dir)
        rel_path = lang_file.relative_to(base_dir)
        display_name = self._make_display_name(namespace, rel_path, is_snbt)

        # Load existing translations (from target file next to source, or external packs)
        existing_entries: dict[str, str] = {}
        existing_array_keys: set[str] = set()
        if target_lang:
            ext = ".snbt" if is_snbt else ".json"
            target_file = lang_file.parent / f"{target_lang}{ext}"
            if target_file.exists():
                try:
                    raw2 = target_file.read_bytes()
                    if is_snbt:
                        parsed, existing_array_keys = self._snbt_parser.parse(raw2)
                    else:
                        parsed = self._json_parser.parse(raw2)
                    existing_entries.update(parsed)
                except Exception:
                    pass
            if not is_snbt and external and namespace in external:
                existing_entries.update(external[namespace])

        existing_map = {namespace: existing_entries} if existing_entries else {}

        mod = ModInfo(
            mod_id=namespace,
            display_name=display_name,
            jar_path=lang_file.parent,
            namespaces={namespace: entries},
            source_type="snbt" if is_snbt else "folder_json",
            source_file=lang_file,
            array_keys=array_keys if not existing_array_keys else array_keys | existing_array_keys,
            existing_translations=existing_map,
        )

        if mod.untranslated_count == 0:
            fully_translated.append(display_name)
            return
        mods.append(mod)

    def _detect_namespace(self, lang_file: Path, base_dir: Path) -> str:
        try:
            rel = lang_file.relative_to(base_dir)
        except ValueError:
            rel = lang_file

        parts = rel.parts

        for i, part in enumerate(parts):
            if part == "assets" and i + 1 < len(parts):
                return parts[i + 1]

        for i, part in enumerate(parts):
            if part == "lang" and i > 0:
                candidate = parts[i - 1]
                if candidate not in ("quests", "chapters", "reward_tables"):
                    return candidate

        for i, part in enumerate(parts):
            if part == "lang" and i >= 2:
                return parts[max(0, i - 2)]

        if len(parts) >= 3:
            return parts[1]

        return parts[0] if parts else "unknown"

    def _make_display_name(
        self, namespace: str, rel_path: Path, is_snbt: bool
    ) -> str:
        name = namespace.replace("_", " ").replace("-", " ").title()
        folder_hint = str(rel_path.parent.parent)
        suffix = " [SNBT]" if is_snbt else ""
        return f"{name} ({folder_hint}){suffix}"
