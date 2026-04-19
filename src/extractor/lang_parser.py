from __future__ import annotations

import json
import re


class LangParser:
    def parse(self, raw_bytes: bytes) -> dict[str, str]:
        text = self._decode(raw_bytes)
        text = self._strip_bom(text)
        try:
            return self._parse_json(text)
        except json.JSONDecodeError:
            text = self._strip_comments(text)
            text = self._fix_trailing_commas(text)
            return self._parse_json(text)

    def _decode(self, raw_bytes: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                return raw_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return raw_bytes.decode("utf-8", errors="replace")

    def _strip_bom(self, text: str) -> str:
        return text.lstrip("\ufeff")

    def _strip_comments(self, text: str) -> str:
        result = []
        i = 0
        in_string = False
        escape_next = False

        while i < len(text):
            ch = text[i]

            if escape_next:
                result.append(ch)
                escape_next = False
                i += 1
                continue

            if ch == "\\" and in_string:
                result.append(ch)
                escape_next = True
                i += 1
                continue

            if ch == '"' and not escape_next:
                in_string = not in_string
                result.append(ch)
                i += 1
                continue

            if not in_string:
                if text[i : i + 2] == "//":
                    newline = text.find("\n", i)
                    if newline == -1:
                        break
                    i = newline
                    continue
                if text[i : i + 2] == "/*":
                    end = text.find("*/", i + 2)
                    if end == -1:
                        break
                    i = end + 2
                    continue

            result.append(ch)
            i += 1

        return "".join(result)

    def _fix_trailing_commas(self, text: str) -> str:
        return re.sub(r",\s*([}\]])", r"\1", text)

    def _parse_json(self, text: str) -> dict[str, str]:
        data = json.loads(text)
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}
