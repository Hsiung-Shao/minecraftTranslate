"""FTB Quests 風格 SNBT 語言檔解析器。

格式範例:
    {
        chapter.xxx.title: "Title text"
        chapter.yyy.desc: ["line 1", "line 2"]
    }

扁平的 key-value 結構，值為字串或字串陣列。不支援深層巢狀。

陣列值會被展開為多個獨立條目 (key[0], key[1], ...)，讓翻譯器可以
逐行處理。寫回時再合併回陣列。
"""
from __future__ import annotations

import re

ARRAY_KEY_PATTERN = re.compile(r"^(.+)\[(\d+)\]$")


class SnbtParser:
    """Parse FTB-style .snbt lang files into flat {key: value} dicts.

    Array values become key[0], key[1], ... entries. array_keys tracks
    which base keys were arrays so we can reconstruct them on output.
    """

    def parse(self, raw: bytes | str) -> tuple[dict[str, str], set[str]]:
        """Return (entries, array_keys).

        array_keys contains the base names of keys that were arrays.
        In entries, those keys appear as "base[0]", "base[1]", etc.
        """
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        text = text.lstrip("\ufeff")

        entries: dict[str, str] = {}
        array_keys: set[str] = set()

        i = 0
        n = len(text)
        while i < n:
            i = self._skip_whitespace(text, i)
            if i >= n or text[i] in "{}":
                i += 1
                continue

            key_end = self._find_key_end(text, i)
            if key_end == -1:
                break
            key = text[i:key_end].strip()
            i = text.index(":", key_end) + 1
            i = self._skip_whitespace(text, i)

            if i >= n:
                break

            if text[i] == "[":
                values, new_i = self._parse_array(text, i)
                array_keys.add(key)
                for idx, v in enumerate(values):
                    entries[f"{key}[{idx}]"] = v
                i = new_i
            elif text[i] == '"':
                value, new_i = self._parse_string(text, i)
                entries[key] = value
                i = new_i
            else:
                end = self._find_line_end(text, i)
                entries[key] = text[i:end].strip()
                i = end

        return entries, array_keys

    def serialize(
        self,
        entries: dict[str, str],
        array_keys: set[str],
    ) -> str:
        """Serialize translated entries back to SNBT format.

        entries may have been translated — array items show up as key[0],
        key[1], etc. We recombine them into arrays for output.
        """
        # Group array entries
        array_items: dict[str, dict[int, str]] = {}
        scalar_items: dict[str, str] = {}

        for key, value in entries.items():
            m = ARRAY_KEY_PATTERN.match(key)
            if m and m.group(1) in array_keys:
                base = m.group(1)
                idx = int(m.group(2))
                array_items.setdefault(base, {})[idx] = value
            else:
                scalar_items[key] = value

        lines = ["{"]
        all_keys = sorted(set(scalar_items.keys()) | set(array_items.keys()))
        for key in all_keys:
            if key in array_items:
                indexed = array_items[key]
                ordered = [indexed[i] for i in sorted(indexed.keys())]
                parts_quoted = ", ".join(self._escape_string(p) for p in ordered)
                lines.append(f"\t{key}: [{parts_quoted}]")
            else:
                lines.append(f"\t{key}: {self._escape_string(scalar_items[key])}")
        lines.append("}")
        return "\n".join(lines) + "\n"

    def _skip_whitespace(self, text: str, i: int) -> int:
        while i < len(text) and text[i] in " \t\r\n":
            i += 1
        return i

    def _find_key_end(self, text: str, start: int) -> int:
        i = start
        while i < len(text) and text[i] not in ":\n":
            i += 1
        return i if i < len(text) and text[i] == ":" else -1

    def _find_line_end(self, text: str, start: int) -> int:
        nl = text.find("\n", start)
        return nl if nl != -1 else len(text)

    def _parse_string(self, text: str, start: int) -> tuple[str, int]:
        assert text[start] == '"'
        i = start + 1
        parts: list[str] = []
        while i < len(text):
            ch = text[i]
            if ch == "\\" and i + 1 < len(text):
                next_ch = text[i + 1]
                if next_ch == "n":
                    parts.append("\n")
                elif next_ch == "t":
                    parts.append("\t")
                elif next_ch == "r":
                    parts.append("\r")
                elif next_ch == '"':
                    parts.append('"')
                elif next_ch == "\\":
                    parts.append("\\")
                else:
                    parts.append(next_ch)
                i += 2
                continue
            if ch == '"':
                return "".join(parts), i + 1
            parts.append(ch)
            i += 1
        return "".join(parts), i

    def _parse_array(self, text: str, start: int) -> tuple[list[str], int]:
        assert text[start] == "["
        i = start + 1
        items: list[str] = []
        while i < len(text):
            i = self._skip_whitespace(text, i)
            if i >= len(text):
                break
            ch = text[i]
            if ch == "]":
                return items, i + 1
            if ch == ",":
                i += 1
                continue
            if ch == '"':
                value, i = self._parse_string(text, i)
                items.append(value)
            else:
                i += 1
        return items, i

    def _escape_string(self, s: str) -> str:
        escaped = (
            s.replace("\\", "\\\\")
            .replace('"', '\\"')
            .replace("\n", "\\n")
            .replace("\t", "\\t")
            .replace("\r", "\\r")
        )
        return f'"{escaped}"'
