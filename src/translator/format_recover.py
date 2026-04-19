"""格式碼遺失自動補救。

當 LLM 翻譯時省略了 `&r`, `&l`, `§6` 等色碼，嘗試按下列策略補回：

策略 A — 開頭/結尾補救：
    原文: "&lTitle&r"   翻譯: "標題"      → 補為 "&l標題&r"

策略 B — 色碼-文字段對齊：
    原文: "A&eB&rC"     翻譯: "甲乙丙"    → 補為 "甲&e乙&r丙"
    (段數完全一致時才套用)

策略 C — 找不到位置的未配對色碼附加到結尾：
    最後手段，至少讓 count 匹配。
"""
from __future__ import annotations

import re

# Legacy Minecraft format codes: &x or §x where x is 0-9, a-f, k-r
FORMAT_CODE_RE = re.compile(r"[&§][0-9a-fk-or]", re.IGNORECASE)
LEADING_CODES_RE = re.compile(r"^(?:[&§][0-9a-fk-or])+", re.IGNORECASE)
TRAILING_CODES_RE = re.compile(r"(?:[&§][0-9a-fk-or])+$", re.IGNORECASE)


def recover_format_codes(original: str, translated: str) -> str:
    """Try to restore missing & / § format codes in translated text.

    Tries multiple strategies and picks the one with fewest missing codes.
    Among equally good results, prefers the shortest (avoid duplicates).
    """
    if not original or not translated:
        return translated

    orig_codes = FORMAT_CODE_RE.findall(original)
    trans_codes = FORMAT_CODE_RE.findall(translated)
    if not orig_codes:
        return translated
    if _multiset_contains(trans_codes, orig_codes):
        return translated

    candidates = [translated]

    # Strategy B first: segmented alignment (usually cleanest)
    seg = _recover_segmented(original, translated)
    if seg != translated:
        candidates.append(seg)

    # Strategy A: leading/trailing on top of best so far
    for base in list(candidates):
        lt = _recover_leading_trailing(original, base)
        if lt != base:
            candidates.append(lt)

    # Strategy C: append anything still missing
    for base in list(candidates):
        appended = _recover_append(original, base)
        if appended != base:
            candidates.append(appended)

    # Pick best: fewest missing codes, then shortest length
    best = min(
        candidates,
        key=lambda s: (_missing_codes(original, s), len(s)),
    )
    return best


def _multiset_contains(haystack: list[str], needle: list[str]) -> bool:
    """Does haystack contain at least as many of each code as needle?"""
    from collections import Counter
    h = Counter(haystack)
    n = Counter(needle)
    for code, count in n.items():
        if h[code] < count:
            return False
    return True


def _missing_codes(original: str, translated: str) -> int:
    """Count of codes present in original but not in translated."""
    from collections import Counter
    orig = Counter(FORMAT_CODE_RE.findall(original))
    trans = Counter(FORMAT_CODE_RE.findall(translated))
    missing = 0
    for code, count in orig.items():
        deficit = count - trans[code]
        if deficit > 0:
            missing += deficit
    return missing


def _is_better(original: str, new: str, old: str) -> bool:
    """Return True if new has fewer missing codes than old."""
    return _missing_codes(original, new) < _missing_codes(original, old)


def _recover_leading_trailing(original: str, translated: str) -> str:
    """Copy any leading or trailing format codes from original to translated."""
    lead_match = LEADING_CODES_RE.search(original)
    trail_match = TRAILING_CODES_RE.search(original)

    result = translated
    if lead_match:
        lead = lead_match.group(0)
        if not LEADING_CODES_RE.match(result) or lead not in result[: len(lead) + 2]:
            # Only add if translated doesn't already start with it
            existing_lead = LEADING_CODES_RE.match(result)
            if not existing_lead or existing_lead.group(0) != lead:
                result = lead + result.lstrip()

    if trail_match:
        trail = trail_match.group(0)
        existing_trail = TRAILING_CODES_RE.search(result)
        if not existing_trail or existing_trail.group(0) != trail:
            result = result.rstrip() + trail

    return result


def _recover_segmented(original: str, translated: str) -> str:
    """Split original by format codes; if translated has same segment count,
    reinsert codes at matching positions.

    Only applies when the alignment looks sensible (segments map cleanly,
    and cut points land on whitespace/punctuation rather than mid-character).
    """
    segments: list[tuple[str, bool]] = []
    last_end = 0
    for m in FORMAT_CODE_RE.finditer(original):
        if m.start() > last_end:
            segments.append((original[last_end : m.start()], False))
        segments.append((m.group(0), True))
        last_end = m.end()
    if last_end < len(original):
        segments.append((original[last_end:], False))

    text_segments = [s for s, is_code in segments if not is_code and s.strip()]
    if len(text_segments) < 2:
        return translated

    # Bail out if the length ratio suggests translation doesn't map 1:1.
    # E.g. long English text -> short Chinese text with many segments becomes messy.
    len_ratio = len(translated) / max(1, sum(len(s) for s in text_segments))
    if len(text_segments) > 3 and (len_ratio < 0.3 or len_ratio > 3.0):
        return translated

    total_orig_len = sum(len(s) for s in text_segments)
    if total_orig_len == 0:
        return translated

    trans_parts: list[str] = []
    cursor = 0
    for i, seg in enumerate(text_segments):
        if i == len(text_segments) - 1:
            trans_parts.append(translated[cursor:])
        else:
            proportion = len(seg) / total_orig_len
            target_len = max(1, int(round(len(translated) * proportion)))
            end = min(len(translated), cursor + target_len)
            new_end = _find_cut_point(translated, cursor, end)
            # If we couldn't find a clean boundary nearby, abort segmented strategy
            if new_end == end and end < len(translated):
                if not _is_clean_cut(translated, end):
                    return translated
            trans_parts.append(translated[cursor:new_end])
            cursor = new_end

    result_parts: list[str] = []
    text_idx = 0
    for seg, is_code in segments:
        if is_code:
            result_parts.append(seg)
        elif seg.strip():
            if text_idx < len(trans_parts):
                result_parts.append(trans_parts[text_idx])
                text_idx += 1
        elif seg:
            # Whitespace-only segment — keep whitespace
            result_parts.append(seg)

    return "".join(result_parts)


def _is_clean_cut(text: str, pos: int) -> bool:
    """True if pos is at a whitespace or punctuation boundary."""
    if pos <= 0 or pos >= len(text):
        return True
    return text[pos - 1] in " 　,.，。;；:：!！?？\n\t" or text[pos] in " 　,.，。;；:：!！?？\n\t"


def _find_cut_point(text: str, start: int, preferred: int) -> int:
    """Find a better cut point near preferred position (prefer punctuation/space)."""
    if preferred >= len(text):
        return len(text)
    # Look within ±3 chars for a break point
    for offset in range(4):
        for pos in (preferred - offset, preferred + offset):
            if start < pos < len(text) and text[pos] in " 　,.，。;；:：!！?？":
                return pos + 1
    return preferred


def _recover_append(original: str, translated: str) -> str:
    """Append any codes still missing to the end of translated."""
    from collections import Counter
    orig = Counter(FORMAT_CODE_RE.findall(original))
    trans = Counter(FORMAT_CODE_RE.findall(translated))

    missing_codes: list[str] = []
    for code, count in orig.items():
        deficit = count - trans[code]
        for _ in range(deficit):
            missing_codes.append(code)

    if not missing_codes:
        return translated

    return translated + "".join(missing_codes)
