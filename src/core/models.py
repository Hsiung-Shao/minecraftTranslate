from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class PipelineState(Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class TargetLanguage:
    code: str
    english_name: str
    native_name: str

    def __hash__(self) -> int:
        return hash(self.code)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, TargetLanguage):
            return self.code == other.code
        return NotImplemented


LANGUAGES: dict[str, TargetLanguage] = {
    "zh_tw": TargetLanguage("zh_tw", "Traditional Chinese", "繁體中文"),
    "zh_cn": TargetLanguage("zh_cn", "Simplified Chinese", "简体中文"),
    "ja_jp": TargetLanguage("ja_jp", "Japanese", "日本語"),
    "ko_kr": TargetLanguage("ko_kr", "Korean", "한국어"),
    "es_es": TargetLanguage("es_es", "Spanish", "Español"),
    "de_de": TargetLanguage("de_de", "German", "Deutsch"),
    "fr_fr": TargetLanguage("fr_fr", "French", "Français"),
    "it_it": TargetLanguage("it_it", "Italian", "Italiano"),
    "pt_br": TargetLanguage("pt_br", "Portuguese (Brazil)", "Português (Brasil)"),
    "ru_ru": TargetLanguage("ru_ru", "Russian", "Русский"),
    "pl_pl": TargetLanguage("pl_pl", "Polish", "Polski"),
    "th_th": TargetLanguage("th_th", "Thai", "ไทย"),
    "vi_vn": TargetLanguage("vi_vn", "Vietnamese", "Tiếng Việt"),
}


@dataclass
class ModInfo:
    mod_id: str
    display_name: str
    jar_path: Path
    namespaces: dict[str, dict[str, str]] = field(default_factory=dict)
    # Source type: "jar" | "folder_json" | "snbt" | "ftb_quests"
    source_type: str = "jar"
    # For non-jar sources: the original file path (used to write output back)
    source_file: Path | None = None
    # For SNBT: preserves keys that had array values (list[str] instead of single str)
    array_keys: set[str] = field(default_factory=set)
    # For ftb_quests: opaque object holding scanner + entries for later writeback
    extra: object = None
    # Existing translations for this mod (namespace -> key -> translated text).
    # Used to skip already-translated keys while still translating new ones.
    existing_translations: dict[str, dict[str, str]] = field(default_factory=dict)

    @property
    def total_entries(self) -> int:
        return sum(len(entries) for entries in self.namespaces.values())

    @property
    def untranslated_count(self) -> int:
        """Count of keys without an existing translation."""
        count = 0
        for ns, entries in self.namespaces.items():
            existing = self.existing_translations.get(ns, {})
            for key in entries:
                if key not in existing:
                    count += 1
        return count


@dataclass
class TranslationUnit:
    key: str
    source_text: str
    translated_text: str | None = None
    mod_id: str = ""
    from_cache: bool = False


@dataclass
class TranslationBatch:
    mod_info: ModInfo
    units: list[TranslationUnit] = field(default_factory=list)
    target_lang: TargetLanguage = field(default_factory=lambda: LANGUAGES["zh_tw"])
