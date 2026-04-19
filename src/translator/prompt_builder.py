from __future__ import annotations

import json

from src.core.models import TargetLanguage, TranslationUnit


class PromptBuilder:
    def build_system_prompt(self, target_lang: TargetLanguage, mod_name: str) -> str:
        return (
            f"You are a professional Minecraft mod translator. "
            f"Translate Minecraft mod UI text from English to "
            f"{target_lang.native_name} ({target_lang.english_name}).\n\n"
            f"Context: You are translating the mod '{mod_name}'.\n\n"
            f"Rules:\n"
            f"1. Preserve ALL placeholders like <T1>, <T2>, <T3> etc. exactly.\n"
            f"2. Keep well-known Minecraft terms if they are commonly untranslated "
            f"in {target_lang.native_name}.\n"
            f"3. Use natural, fluent language that Minecraft players would understand.\n"
            f"4. Return ONLY a valid JSON object with the same keys and translated values.\n"
            f"5. Do NOT translate the JSON keys.\n"
            f"6. Do NOT add explanations or commentary outside the JSON."
        )

    def build_translation_prompt(
        self, units: list[TranslationUnit]
    ) -> str:
        texts = {unit.key: unit.source_text for unit in units}
        return (
            "Translate the following JSON values to the target language. "
            "Return a JSON object with the same keys and translated values:\n\n"
            + json.dumps(texts, ensure_ascii=False, indent=2)
        )

    def parse_response(
        self, response_text: str, expected_keys: list[str]
    ) -> dict[str, str]:
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            cleaned = self._extract_json_block(response_text)
            data = json.loads(cleaned)

        if not isinstance(data, dict):
            return {}

        return {str(k): str(v) for k, v in data.items() if str(k) in expected_keys}

    def _extract_json_block(self, text: str) -> str:
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines)

        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            return text[start : end + 1]

        return text
