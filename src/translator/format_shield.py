from __future__ import annotations

import re
from dataclasses import dataclass, field

PLACEHOLDER_PREFIX = "\ue000"
PLACEHOLDER_SUFFIX = "\ue001"

# Short formatting tags that models can preserve on their own.
PASSTHROUGH_TAGS = re.compile(
    r"</?(?:r|n|i|b|u|s|imp|item|bold|italic|underline|obf|reset|br|line|ns|link|"
    r"formatting|text|color|key|action|click|hover|highlight|glow|tip|info|warning|"
    r"error|success|gold|red|green|blue|yellow|aqua|gray|dark_red|dark_green|"
    r"dark_blue|dark_aqua|dark_gray|dark_purple|light_purple|white|black|rf|range)>",
    re.IGNORECASE,
)

# Patterns for passthrough format codes (not masked, validated after translation)
PASSTHROUGH_COLOR_SECTION = re.compile(r"§[0-9a-fk-or]", re.IGNORECASE)
PASSTHROUGH_COLOR_AMP = re.compile(r"&[0-9a-fk-or]", re.IGNORECASE)
PASSTHROUGH_MACRO = re.compile(r"\$\([^)]+\)")

ALL_PASSTHROUGH_PATTERNS = [
    PASSTHROUGH_TAGS,
    PASSTHROUGH_COLOR_SECTION,
    PASSTHROUGH_COLOR_AMP,
    PASSTHROUGH_MACRO,
]


@dataclass
class MaskedText:
    masked_string: str
    token_map: dict[str, str] = field(default_factory=dict)


class FormatShield:
    PATTERNS: list[tuple[str, re.Pattern]] = [
        ("color_section", re.compile(r"§[0-9a-fk-or]", re.IGNORECASE)),
        ("color_amp", re.compile(r"&[0-9a-fk-or]", re.IGNORECASE)),
        ("fmt_indexed", re.compile(r"%\d+\$[a-zA-Z]")),
        ("fmt_float", re.compile(r"%\.?\d*[dfsxXobeEgG%]")),
        ("template_dollar", re.compile(r"\$\{[^}]+\}")),
        ("macro_paren", re.compile(r"\$\([^)]+\)")),
        ("xml_tag", re.compile(r"<[^>]{1,50}>")),
        ("mc_ref", re.compile(r"\[[a-z0-9_.-]+:[a-z0-9_./-]+\]")),
        ("keybind", re.compile(r"%%[a-zA-Z._]+")),
        ("braces", re.compile(r"\{[^}]+\}")),
        ("md_link", re.compile(r"\]\([^)]+\)")),
        ("newline", re.compile(r"\\n")),
    ]

    # These pattern names are passthrough — never masked, model sees them directly
    PASSTHROUGH_NAMES = {"color_section", "color_amp", "macro_paren"}

    def _should_mask(self, name: str, matched_text: str) -> bool:
        if name in self.PASSTHROUGH_NAMES:
            return False
        if name == "xml_tag":
            if PASSTHROUGH_TAGS.fullmatch(matched_text):
                return False
        return True

    def mask(self, text: str) -> MaskedText:
        matches: list[tuple[int, int, str]] = []

        for name, pattern in self.PATTERNS:
            for m in pattern.finditer(text):
                start, end = m.start(), m.end()
                if not any(s <= start < e for s, e, _ in matches):
                    original = m.group(0)
                    if self._should_mask(name, original):
                        matches.append((start, end, original))

        matches.sort(key=lambda x: x[0])

        token_map: dict[str, str] = {}
        reverse_map: dict[str, str] = {}
        counter = 0
        result_parts: list[str] = []
        last_end = 0

        for start, end, original in matches:
            result_parts.append(text[last_end:start])

            if original not in reverse_map:
                counter += 1
                token_map[f"<T{counter}>"] = original
                reverse_map[original] = f"<T{counter}>"

            result_parts.append(reverse_map[original])
            last_end = end

        result_parts.append(text[last_end:])

        return MaskedText(masked_string="".join(result_parts), token_map=token_map)

    def unmask(self, masked_text: str, token_map: dict[str, str]) -> str:
        result = masked_text
        for placeholder, original in sorted(
            token_map.items(), key=lambda x: -int(x[0][2:-1])
        ):
            result = result.replace(placeholder, original)
        return result

    def to_llm_format(self, masked: MaskedText) -> str:
        result = masked.masked_string
        for key in masked.token_map:
            num = key[2:-1]
            internal = f"{PLACEHOLDER_PREFIX}{num}{PLACEHOLDER_SUFFIX}"
            result = result.replace(internal, key)
        return result

    def from_llm_format(self, llm_text: str, token_map: dict[str, str]) -> str:
        result = llm_text
        for key, original in token_map.items():
            result = result.replace(key, original)
        return result

    def validate(self, original: str, translated: str) -> list[str]:
        issues = []
        seen: set[str] = set()

        # Check masked tokens (complex format codes)
        original_masked = self.mask(original)
        for _placeholder, token in original_masked.token_map.items():
            if token in seen:
                continue
            seen.add(token)
            count_original = original.count(token)
            count_translated = translated.count(token)
            if count_translated < count_original:
                issues.append(
                    f"Missing format code '{token}': "
                    f"expected {count_original}, found {count_translated}"
                )

        # Check all passthrough patterns
        for pattern in ALL_PASSTHROUGH_PATTERNS:
            for m in pattern.finditer(original):
                token = m.group(0)
                if token in seen:
                    continue
                seen.add(token)
                count_original = original.count(token)
                count_translated = translated.count(token)
                if count_translated < count_original:
                    issues.append(
                        f"Missing format code '{token}': "
                        f"expected {count_original}, found {count_translated}"
                    )

        return issues

    def is_translatable(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        masked = self.mask(text)
        remaining = self.to_llm_format(masked)
        for placeholder in masked.token_map:
            remaining = remaining.replace(placeholder, "")
        # Strip all passthrough patterns
        for pattern in ALL_PASSTHROUGH_PATTERNS:
            remaining = pattern.sub("", remaining)
        remaining = remaining.strip()
        if not remaining:
            return False
        if re.match(r"^[a-z0-9_.:-]+$", remaining):
            return False
        return True
