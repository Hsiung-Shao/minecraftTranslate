from __future__ import annotations

import json
from pathlib import Path


class TerminologyDict:
    def __init__(self, dict_path: Path | None = None) -> None:
        self._terms: dict[str, dict[str, str]] = {}
        if dict_path and dict_path.exists():
            self._load(dict_path)

    def _load(self, path: Path) -> None:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key, value in data.items():
            if key.startswith("_"):
                continue
            if isinstance(value, dict):
                self._terms[key.lower()] = value

    def apply(self, text: str, target_lang: str) -> str:
        result = text
        for term, translations in self._terms.items():
            if target_lang in translations:
                import re
                pattern = re.compile(re.escape(term), re.IGNORECASE)
                result = pattern.sub(translations[target_lang], result)
        return result

    def get_translation(self, term: str, target_lang: str) -> str | None:
        entry = self._terms.get(term.lower())
        if entry and target_lang in entry:
            return entry[target_lang]
        return None
