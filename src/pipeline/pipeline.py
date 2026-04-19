from __future__ import annotations

from pathlib import Path

from src.cache.cache_store import CacheStore
from src.core.config import AppConfig
from src.core.events import EventBus, LogEvent
from src.core.models import LANGUAGES, ModInfo, TargetLanguage
from src.extractor.folder_scanner import FolderScanner
from src.extractor.ftb_quests_scanner import FTBQuestsScanner, QuestFileEntry
from src.extractor.jar_scanner import JarScanner
from src.extractor.pack_format_detector import detect_pack_format
from src.extractor.resourcepack_scanner import ResourcePackScanner
from src.extractor.snbt_parser import SnbtParser
from src.packager.resource_pack import ResourcePackBuilder
from src.pipeline.progress import CancelledError, ProgressTracker
from src.translator.batch_processor import BatchProcessor
from src.translator.engine import create_engine
from src.translator.format_shield import FormatShield
from src.translator.prompt_builder import PromptBuilder


class TranslationPipeline:
    def __init__(self, config: AppConfig, event_bus: EventBus) -> None:
        self.config = config
        self.event_bus = event_bus
        self.scanner = JarScanner()
        self.folder_scanner = FolderScanner()
        self.resourcepack_scanner = ResourcePackScanner()
        self.ftb_quests_scanner = FTBQuestsScanner()
        self.snbt_parser = SnbtParser()
        self.engine = create_engine(config)
        self.shield = FormatShield()
        self.cache = CacheStore(config.cache_db_path)
        self.prompt_builder = PromptBuilder()
        self.progress = ProgressTracker(event_bus)
        self.processor = BatchProcessor(
            engine=self.engine,
            shield=self.shield,
            cache=self.cache,
            prompt_builder=self.prompt_builder,
            config=config,
            event_bus=event_bus,
        )

    def run(
        self,
        mods_folder: Path,
        target_lang_code: str,
        selected_mods: list[ModInfo] | None = None,
    ) -> Path | None:
        target_lang = LANGUAGES.get(target_lang_code)
        if not target_lang:
            self._log(f"未知的語言: {target_lang_code}", "error")
            self.progress.error()
            return None

        try:
            if selected_mods is not None:
                mods = selected_mods
                self._log(f"翻譯選定的 {len(mods)} 個模組")
            else:
                mods, skipped = self._scan_all(mods_folder, target_lang_code)
                if skipped:
                    self._log(
                        f"已跳過 {len(skipped)} 個已有 {target_lang_code} 翻譯的模組",
                        "info",
                    )

                if not mods:
                    self._log("未找到需要翻譯的模組。", "warning")
                    self.progress.complete()
                    return None

            total_entries = sum(m.total_entries for m in mods)
            self._log(f"共 {len(mods)} 個模組，{total_entries} 條字串待翻譯")

            self.progress.start(len(mods))

            # Auto-detect pack_format from the game dir / mod jars
            game_dir = self._detect_game_dir(mods_folder)
            if game_dir:
                pack_format, source = detect_pack_format(game_dir, mods_folder)
                self._log(f"自動偵測資源包格式: {pack_format} (來源: {source})")
            else:
                pack_format = self.config.pack_format

            output_path = self._get_output_path(target_lang)
            snbt_outputs: list[Path] = []
            ftb_quests_outputs: list[Path] = []
            with ResourcePackBuilder(
                output_path,
                self.config.resource_pack_name,
                pack_format,
                target_lang,
            ) as packager:
                for i, mod in enumerate(mods):
                    self.progress.wait_if_paused()
                    self.progress.check_cancelled()

                    self._log(
                        f"處理中: {mod.display_name} ({i + 1}/{len(mods)})"
                    )

                    try:
                        translated = self.processor.process_mod(mod, target_lang)

                        if mod.source_type == "snbt":
                            snbt_path = self._write_snbt_output(
                                mod, translated, target_lang
                            )
                            if snbt_path:
                                snbt_outputs.append(snbt_path)
                        elif mod.source_type == "ftb_quests":
                            written = self._write_ftb_quests_output(mod, translated)
                            ftb_quests_outputs.extend(written)
                        else:
                            for namespace, entries in translated.items():
                                packager.add_lang_file(namespace, entries)
                    except Exception as e:
                        self._log(
                            f"處理 {mod.display_name} 時發生錯誤: {e}",
                            "error",
                        )
                        continue

                    self.progress.update(i + 1, mod.display_name)

            self.progress.complete()
            self._log(f"資源包已儲存至: {output_path}")
            for snbt_path in snbt_outputs:
                self._log(f"SNBT 已寫入: {snbt_path}")
            if ftb_quests_outputs:
                self._log(f"FTB Quests 已更新 {len(ftb_quests_outputs)} 個 SNBT 檔")
            return output_path

        except CancelledError:
            self._log("翻譯已被使用者取消。", "warning")
            return None
        except Exception as e:
            self._log(f"管線錯誤: {e}", "error")
            self.progress.error()
            return None
        finally:
            self.cache.close()

    def analyze(
        self, mods_folder: Path, target_lang_code: str = ""
    ) -> tuple[list[ModInfo], list[str]]:
        return self._scan_all(mods_folder, target_lang_code)

    def _scan_all(
        self, mods_folder: Path, target_lang_code: str
    ) -> tuple[list[ModInfo], list[str]]:
        self._log("正在掃描 mods 資料夾...")

        # Step 1: load existing translations from all resource packs
        game_dir = self._detect_game_dir(mods_folder)
        external_translations: dict[str, dict[str, str]] = {}
        if game_dir:
            resourcepacks_dir = game_dir / "resourcepacks"
            if resourcepacks_dir.is_dir():
                external_translations = self.resourcepack_scanner.load_translations(
                    resourcepacks_dir, target_lang_code
                )
                if external_translations:
                    total_keys = sum(len(v) for v in external_translations.values())
                    self._log(
                        f"從 resourcepacks 找到 {len(external_translations)} 個 "
                        f"namespace 共 {total_keys} 條既有翻譯"
                    )

        # Step 2: JAR mods — now returns mods with partial translations too
        mods, fully_translated = self.scanner.scan_folder(
            mods_folder, target_lang_code, external_translations
        )
        jar_count = len(mods)
        jar_fully = len(fully_translated)

        # Step 3: folder lang files (JSON + SNBT)
        folder_count = 0
        folder_fully = 0
        ftb_quests_count = 0
        if game_dir:
            self._log(f"正在掃描遊戲目錄: {game_dir}")
            folder_mods, folder_done = self.folder_scanner.scan_game_dir(
                game_dir, target_lang_code, external_translations
            )
            mods.extend(folder_mods)
            fully_translated.extend(folder_done)
            folder_count = len(folder_mods)
            folder_fully = len(folder_done)

            # Step 4: FTB Quests embedded text (no existing check possible — rewrites in place)
            ftb_mod = self._scan_ftb_quests_embedded(game_dir)
            if ftb_mod:
                mods.append(ftb_mod)
                ftb_quests_count = 1

        total_untranslated = sum(m.untranslated_count for m in mods)
        self._log(
            f"找到 {jar_count} 個 JAR 模組 + {folder_count} 個資料夾來源 "
            f"+ {ftb_quests_count} 個 FTB Quests 嵌入來源"
        )
        self._log(
            f"已完整翻譯: JAR {jar_fully} + 資料夾 {folder_fully} 個；"
            f"待翻譯 {total_untranslated} 條"
        )
        return mods, fully_translated

    def _scan_ftb_quests_embedded(self, game_dir: Path) -> ModInfo | None:
        entries = self.ftb_quests_scanner.scan(game_dir)
        if not entries:
            return None

        # Build flat namespace: unique key per string to translate
        namespace: dict[str, str] = {}
        entry_meta: dict[str, tuple[QuestFileEntry, int]] = {}
        for i, entry in enumerate(entries):
            for j, s in enumerate(entry.strings):
                if not s or not s.strip():
                    continue
                key = f"ftbq_{i}_{j}"
                namespace[key] = s
                entry_meta[key] = (entry, j)

        if not namespace:
            return None

        total_strings = len(namespace)
        total_files = len(set(e.file_path for e in entries))

        return ModInfo(
            mod_id="ftbquests_embedded",
            display_name=f"FTB Quests 任務文字 ({total_files} 檔, {total_strings} 條)",
            jar_path=game_dir / "config" / "ftbquests",
            namespaces={"ftbquests_embedded": namespace},
            source_type="ftb_quests",
            extra=entry_meta,
        )

    def _detect_game_dir(self, mods_folder: Path) -> Path | None:
        if mods_folder.name == "mods":
            parent = mods_folder.parent
            if (parent / "config").is_dir() or (parent / "options.txt").exists():
                return parent

        if (mods_folder / "config").is_dir():
            return mods_folder

        return None

    def _write_snbt_output(
        self,
        mod: ModInfo,
        translated: dict[str, dict[str, str]],
        target_lang: TargetLanguage,
    ) -> Path | None:
        if not mod.source_file:
            self._log(f"  警告: {mod.display_name} 無 source_file", "warning")
            return None

        entries: dict[str, str] = {}
        for ns_entries in translated.values():
            entries.update(ns_entries)

        if not entries:
            return None

        output_path = mod.source_file.parent / f"{target_lang.code}.snbt"
        try:
            content = self.snbt_parser.serialize(entries, mod.array_keys)
            output_path.write_text(content, encoding="utf-8")
            return output_path
        except Exception as e:
            self._log(f"  寫入 SNBT 失敗: {e}", "error")
            return None

    def _write_ftb_quests_output(
        self,
        mod: ModInfo,
        translated: dict[str, dict[str, str]],
    ) -> list[Path]:
        """Write translated FTB Quests text back to original .snbt files."""
        entry_meta: dict = mod.extra or {}
        if not entry_meta:
            return []

        # Get the flat {key: translated_text} mapping
        translated_flat: dict[str, str] = {}
        for ns_entries in translated.values():
            translated_flat.update(ns_entries)

        # Group translations by file path, collect (string_start, string_end) -> new text
        file_translations: dict[Path, dict[tuple[int, int], str]] = {}
        file_entries: dict[Path, list[QuestFileEntry]] = {}

        for key, (entry, str_idx) in entry_meta.items():
            if key not in translated_flat:
                continue
            new_text = translated_flat[key]
            s_start, s_end = entry.string_ranges[str_idx]
            file_translations.setdefault(entry.file_path, {})[(s_start, s_end)] = new_text
            if entry not in file_entries.setdefault(entry.file_path, []):
                file_entries[entry.file_path].append(entry)

        written: list[Path] = []
        for file_path, translations in file_translations.items():
            try:
                self.ftb_quests_scanner.write_translated(
                    file_path, file_entries[file_path], translations
                )
                written.append(file_path)
            except Exception as e:
                self._log(f"  寫回 {file_path.name} 失敗: {e}", "error")

        return written

    def _get_output_path(self, target_lang: TargetLanguage) -> Path:
        output_dir = Path(self.config.output_folder or ".")
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self.config.resource_pack_name}_{target_lang.code}.zip"
        return output_dir / filename

    def _log(self, message: str, level: str = "info") -> None:
        self.event_bus.publish_threadsafe("log", LogEvent(message, level))
