"""FTB Quests 嵌入式文字掃描器。

從 config/ftbquests/quests/chapters/*.snbt 和 reward_tables/*.snbt
直接擷取可翻譯欄位 (title, subtitle, description, hover 等)。

不走正規 SNBT 解析器。使用 regex 擷取目標欄位，再做文字替換，
避免處理複雜的深層巢狀結構。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


# Quoted string: "..." with escaped quotes supported
_QUOTED_STRING = r'"(?:[^"\\]|\\.)*"'

# 可翻譯欄位名（key: value 或 key: [array]）
_TRANSLATABLE_FIELDS = (
    "title",
    "subtitle",
    "description",
    "hover",
    "text",
    "name",
    "custom_click_event",
)

# Pattern to find "fieldname: <string-or-array>" at indented positions
# Matches one of: field: "string"  OR  field: ["str1", "str2", ...]
def _field_pattern(field: str) -> re.Pattern:
    # Non-capturing: field name, then colon and optional whitespace
    # Group 1 = "string" | [...strings...]
    return re.compile(
        rf'(?<![a-zA-Z_]){re.escape(field)}\s*:\s*'
        rf'({_QUOTED_STRING}|\[(?:\s*{_QUOTED_STRING}\s*,?\s*)*\])',
        re.MULTILINE,
    )


_FIELD_PATTERNS = {f: _field_pattern(f) for f in _TRANSLATABLE_FIELDS}
_STRING_RE = re.compile(_QUOTED_STRING)


@dataclass
class QuestFileEntry:
    """Represents a single translatable occurrence in a quest SNBT file."""
    file_path: Path
    field_name: str
    match_start: int
    match_end: int
    is_array: bool
    strings: list[str]  # Original string content (unescaped)
    # For arrays: list of (start, end) ranges of each string within match
    string_ranges: list[tuple[int, int]]


class FTBQuestsScanner:
    QUESTS_SUBPATH = Path("config/ftbquests/quests")
    SCAN_SUBDIRS = ("chapters", "reward_tables")
    TARGET_FILENAME = "data.snbt"

    def scan(self, game_dir: Path) -> list[QuestFileEntry]:
        """Scan all quest SNBT files and return translatable entries."""
        entries: list[QuestFileEntry] = []
        quests_dir = game_dir / self.QUESTS_SUBPATH

        if not quests_dir.is_dir():
            return entries

        files: list[Path] = []
        # chapter_groups.snbt, data.snbt at root of quests/
        for f in quests_dir.glob("*.snbt"):
            if f.is_file():
                files.append(f)
        # chapters/ and reward_tables/
        for sub in self.SCAN_SUBDIRS:
            sub_dir = quests_dir / sub
            if sub_dir.is_dir():
                for f in sub_dir.glob("*.snbt"):
                    files.append(f)

        for file_path in files:
            try:
                entries.extend(self._scan_file(file_path))
            except Exception:
                continue

        return entries

    def _scan_file(self, file_path: Path) -> list[QuestFileEntry]:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        entries: list[QuestFileEntry] = []

        for field_name, pattern in _FIELD_PATTERNS.items():
            for m in pattern.finditer(text):
                value_text = m.group(1)
                value_start = m.start(1)

                if value_text.startswith("["):
                    strings, ranges = self._extract_array_strings(
                        value_text, value_start
                    )
                    if strings:
                        entries.append(QuestFileEntry(
                            file_path=file_path,
                            field_name=field_name,
                            match_start=m.start(),
                            match_end=m.end(),
                            is_array=True,
                            strings=strings,
                            string_ranges=ranges,
                        ))
                else:
                    # Single string
                    unescaped = self._unescape(value_text[1:-1])
                    if unescaped.strip():
                        entries.append(QuestFileEntry(
                            file_path=file_path,
                            field_name=field_name,
                            match_start=m.start(),
                            match_end=m.end(),
                            is_array=False,
                            strings=[unescaped],
                            string_ranges=[(value_start, value_start + len(value_text))],
                        ))

        return entries

    def _extract_array_strings(
        self, array_text: str, base_offset: int
    ) -> tuple[list[str], list[tuple[int, int]]]:
        strings: list[str] = []
        ranges: list[tuple[int, int]] = []
        for m in _STRING_RE.finditer(array_text):
            raw = m.group(0)
            unescaped = self._unescape(raw[1:-1])
            # Keep empty strings as placeholders so we can write back array shape
            strings.append(unescaped)
            ranges.append((base_offset + m.start(), base_offset + m.end()))
        return strings, ranges

    def _unescape(self, s: str) -> str:
        return (
            s.replace("\\n", "\n")
            .replace("\\t", "\t")
            .replace('\\"', '"')
            .replace("\\\\", "\\")
        )

    def escape(self, s: str) -> str:
        return (
            s.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\t", "\\t")
        )

    def write_translated(
        self,
        file_path: Path,
        entries: list[QuestFileEntry],
        translations: dict[tuple[int, int], str],
    ) -> None:
        """Apply translations to a single quest file.

        translations: mapping from (match_start, string_index) -> translated text
        Actually we use (string_start, string_end) keys from string_ranges.
        """
        text = file_path.read_text(encoding="utf-8", errors="replace")

        # Collect all replacements (pos_start, pos_end, new_text)
        replacements: list[tuple[int, int, str]] = []
        for entry in entries:
            if entry.file_path != file_path:
                continue
            for i, (s, e) in enumerate(entry.string_ranges):
                key = (s, e)
                if key in translations:
                    new_str = translations[key]
                    replacements.append((s, e, f'"{self.escape(new_str)}"'))

        # Apply from end to start to preserve positions
        replacements.sort(key=lambda x: -x[0])
        chars = list(text)
        for start, end, new_text in replacements:
            chars[start:end] = new_text

        file_path.write_text("".join(chars), encoding="utf-8")
