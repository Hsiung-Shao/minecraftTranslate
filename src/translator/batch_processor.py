from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.cache.cache_store import CacheStore
from src.core.config import AppConfig
from src.core.events import BatchProgressEvent, EventBus, LogEvent
from src.core.models import ModInfo, TargetLanguage, TranslationUnit
from src.translator.engine import TranslationEngine
from src.translator.format_recover import recover_format_codes
from src.translator.format_shield import FormatShield
from src.translator.prompt_builder import PromptBuilder


class BatchProcessor:
    def __init__(
        self,
        engine: TranslationEngine,
        shield: FormatShield,
        cache: CacheStore,
        prompt_builder: PromptBuilder,
        config: AppConfig,
        event_bus: EventBus,
    ) -> None:
        self.engine = engine
        self.shield = shield
        self.cache = cache
        self.prompt_builder = prompt_builder
        self.batch_size = config.batch_size
        self.max_workers = max(1, config.max_workers)
        self.event_bus = event_bus

        # Dynamically compute char limits from context_tokens.
        # Rough estimate: ~3 chars per token for mixed English/Chinese.
        # Budget allocation:
        #   60% of context for output (thinking + JSON translation)
        #   Of remaining 40%, use 70% for user prompt input
        # This leaves headroom for system prompt, JSON structure, and thinking.
        available_tokens = max(1024, config.context_tokens - config.reserved_tokens)
        chars_per_token = 3
        input_budget_tokens = int(available_tokens * 0.4 * 0.7)
        self.max_batch_chars = input_budget_tokens * chars_per_token
        self.max_single_chars = int(self.max_batch_chars * 0.6)

    def process_mod(
        self, mod: ModInfo, target_lang: TargetLanguage
    ) -> dict[str, dict[str, str]]:
        results: dict[str, dict[str, str]] = {}

        for namespace, entries in mod.namespaces.items():
            existing_ns = mod.existing_translations.get(namespace, {})

            # Split into: translatable-and-missing / already-translated / non-translatable
            units: list[TranslationUnit] = []
            non_translatable: dict[str, str] = {}
            already_done: dict[str, str] = {}
            for k, v in entries.items():
                if not self.shield.is_translatable(v):
                    non_translatable[k] = v
                elif k in existing_ns:
                    already_done[k] = existing_ns[k]
                else:
                    units.append(TranslationUnit(
                        key=k, source_text=v, mod_id=mod.mod_id
                    ))

            translated: dict[str, str] = {}
            translated.update(non_translatable)
            translated.update(already_done)

            if already_done:
                self.event_bus.publish_threadsafe(
                    "log",
                    LogEvent(
                        f"  {namespace}: 已有 {len(already_done)} 條翻譯，"
                        f"新增 {len(units)} 條待翻譯"
                    ),
                )

            batches = self._split_into_batches(units)
            total_batches = len(batches)

            lock = threading.Lock()
            progress = {"cache_hits": 0, "strings_done": 0, "batches_done": 0}

            def _on_batch_done(batch_result: list[TranslationUnit]) -> None:
                with lock:
                    for unit in batch_result:
                        if unit.translated_text is not None:
                            translated[unit.key] = unit.translated_text
                            progress["strings_done"] += 1
                            if unit.from_cache:
                                progress["cache_hits"] += 1
                    progress["batches_done"] += 1

                    self.event_bus.publish_threadsafe(
                        "batch_progress",
                        BatchProgressEvent(
                            mod_name=mod.display_name,
                            batch_current=progress["batches_done"],
                            batch_total=total_batches,
                            strings_done=progress["strings_done"],
                            strings_total=len(units),
                            cache_hits=progress["cache_hits"],
                        ),
                    )

            if self.max_workers <= 1 or total_batches <= 1:
                for batch in batches:
                    result = self._process_single_batch(
                        batch, target_lang, mod.display_name
                    )
                    _on_batch_done(result)
            else:
                with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                    futures = {
                        pool.submit(
                            self._process_single_batch,
                            batch, target_lang, mod.display_name,
                        ): idx
                        for idx, batch in enumerate(batches)
                    }
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            _on_batch_done(result)
                        except Exception as e:
                            self.event_bus.publish_threadsafe(
                                "log",
                                LogEvent(f"  批次處理錯誤: {e}", level="error"),
                            )

            self.event_bus.publish_threadsafe(
                "log",
                LogEvent(
                    f"  {namespace}: {progress['strings_done']}/{len(units)} 條已翻譯 "
                    f"(快取命中: {progress['cache_hits']})"
                ),
            )
            results[namespace] = translated

        return results

    def _split_into_batches(
        self, units: list[TranslationUnit]
    ) -> list[list[TranslationUnit]]:
        batches: list[list[TranslationUnit]] = []
        current: list[TranslationUnit] = []
        current_chars = 0

        for unit in units:
            unit_chars = len(unit.source_text)

            # Oversized single string → flush current batch, send it alone
            if unit_chars >= self.max_single_chars:
                if current:
                    batches.append(current)
                    current = []
                    current_chars = 0
                batches.append([unit])
                continue

            # Would exceed char budget or count limit → flush current batch
            if current and (
                current_chars + unit_chars > self.max_batch_chars
                or len(current) >= self.batch_size
            ):
                batches.append(current)
                current = []
                current_chars = 0

            current.append(unit)
            current_chars += unit_chars

        if current:
            batches.append(current)

        return batches

    def _process_single_batch(
        self,
        batch: list[TranslationUnit],
        target_lang: TargetLanguage,
        mod_name: str,
    ) -> list[TranslationUnit]:
        masked_map: dict[str, dict] = {}
        for unit in batch:
            masked = self.shield.mask(unit.source_text)
            masked_map[unit.key] = {
                "unit": unit,
                "masked": masked,
            }

        cache_keys = [
            (unit.source_text, target_lang.code)
            for unit in batch
        ]
        cached = self.cache.get_batch(cache_keys)

        to_translate: dict[str, str] = {}
        for unit in batch:
            cache_key = (unit.source_text, target_lang.code)
            if cache_key in cached:
                unit.translated_text = cached[cache_key]
                unit.from_cache = True
            else:
                info = masked_map[unit.key]
                to_translate[unit.key] = self.shield.to_llm_format(info["masked"])

        if to_translate:
            try:
                raw_translations = self.engine.translate_batch(
                    to_translate, target_lang.english_name, mod_name
                )
            except Exception as e:
                self.event_bus.publish_threadsafe(
                    "log",
                    LogEvent(f"  Translation error: {e}", level="error"),
                )
                return batch

            new_cache_entries: list[tuple[str, str, str]] = []

            for unit in batch:
                if unit.from_cache or unit.key not in raw_translations:
                    continue

                info = masked_map[unit.key]
                raw = raw_translations[unit.key]
                unmasked = self.shield.from_llm_format(raw, info["masked"].token_map)

                issues = self.shield.validate(unit.source_text, unmasked)
                if issues:
                    recovered = recover_format_codes(unit.source_text, unmasked)
                    issues_after = self.shield.validate(unit.source_text, recovered)
                    if len(issues_after) < len(issues):
                        fixed = len(issues) - len(issues_after)
                        self.event_bus.publish_threadsafe(
                            "log",
                            LogEvent(
                                f"  自動修復 [{unit.key}]: 補回 {fixed} 個格式碼"
                            ),
                        )
                        unmasked = recovered
                        issues = issues_after
                    if issues:
                        self.event_bus.publish_threadsafe(
                            "log",
                            LogEvent(
                                f"  格式仍缺 [{unit.key}]: {'; '.join(issues)}",
                                level="warning",
                            ),
                        )

                unit.translated_text = unmasked
                new_cache_entries.append(
                    (unit.source_text, target_lang.code, unmasked)
                )

            if new_cache_entries:
                self.cache.put_batch(new_cache_entries)

        return batch
