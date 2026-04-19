from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod

import requests

from src.core.config import AppConfig
from src.core.exceptions import ConnectionError, ModelError, TranslationError


def build_system_prompt(target_lang: str, mod_name: str) -> str:
    return (
        f"You are a Minecraft mod translator. "
        f"Translate mod '{mod_name}' from English to {target_lang}.\n\n"
        f"CRITICAL - Format codes MUST be preserved EXACTLY:\n"
        f"  &0-9, &a-f, &k-r  → Minecraft legacy color/format codes\n"
        f"  §0-9, §a-f, §k-r  → Modern Minecraft format codes\n"
        f"  <T1>, <T2>, ...   → Masked tokens (keep as-is)\n"
        f"  <r>, <n>, <imp>, <item>, <rf>  → Markup tags\n"
        f"  $(l), $(k:use), $(...)  → Patchouli macros\n\n"
        f"Examples:\n"
        f"  Input:  '&lDiamond Sword&r deals &c10&r damage'\n"
        f"  CORRECT: '&l鑽石劍&r 造成 &c10&r 點傷害'\n"
        f"  WRONG:   '鑽石劍造成 10 點傷害'  (missing &l &r &c &r)\n\n"
        f"Other rules:\n"
        f"1. Keep proper nouns commonly left untranslated in {target_lang}.\n"
        f"2. Use natural {target_lang} for Minecraft players.\n"
        f"3. Output ONLY a raw JSON object. No markdown, no code blocks, no explanation.\n"
        f"4. Do NOT translate keys, only values.\n"
        f"5. Count every &x and §x in the input — your output MUST contain the same count of each."
    )


def build_user_prompt(texts: dict[str, str]) -> str:
    return (
        "Translate the following JSON values. "
        "Return a JSON object with the same keys and translated values:\n\n"
        + json.dumps(texts, ensure_ascii=False, indent=2)
    )


def extract_json(text: str) -> str:
    text = text.strip()
    if text.startswith("{"):
        return text
    code_block = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if code_block:
        return code_block.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def parse_response(response_text: str, expected_keys: list[str]) -> dict[str, str]:
    cleaned = extract_json(response_text)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise TranslationError(
            f"無法解析 API 回應為 JSON: {e}\n回應內容: {response_text[:200]}"
        ) from e
    if not isinstance(data, dict):
        raise TranslationError("回應不是 JSON 物件")
    return {str(k): str(v) for k, v in data.items() if str(k) in expected_keys}


class TranslationEngine(ABC):
    @abstractmethod
    def translate_batch(
        self, texts: dict[str, str], target_lang: str, mod_name: str
    ) -> dict[str, str]:
        ...

    @abstractmethod
    def check_connection(self) -> bool:
        ...

    @abstractmethod
    def list_models(self) -> list[str]:
        ...

    def get_loaded_model(self) -> str | None:
        return None


# ─── 本地模型引擎 (LM Studio, Ollama, 其他 OpenAI 相容後端) ───

class LocalModelEngine(TranslationEngine):
    def __init__(self, config: AppConfig) -> None:
        self.base_url = config.api_url.rstrip("/")
        self.model = config.api_model
        self.temperature = config.temperature
        self.max_retries = config.max_retries
        self.max_tokens = max(4096, int(config.context_tokens * 0.6))
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def check_connection(self) -> bool:
        try:
            resp = self.session.get(f"{self.base_url}/models", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False

    def list_models(self) -> list[str]:
        try:
            resp = self.session.get(f"{self.base_url}/models", timeout=10)
            resp.raise_for_status()
            data = resp.json()
            return [m["id"] for m in data.get("data", [])]
        except requests.RequestException as e:
            raise ConnectionError(f"無法連線至 API: {e}") from e

    def get_loaded_model(self) -> str | None:
        try:
            resp = self.session.post(
                f"{self.base_url}/chat/completions",
                json={
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("model", data.get("id", "unknown"))
            return None
        except requests.RequestException:
            return None

    def translate_batch(
        self, texts: dict[str, str], target_lang: str, mod_name: str
    ) -> dict[str, str]:
        if not texts:
            return {}
        system_prompt = build_system_prompt(target_lang, mod_name)
        user_prompt = build_user_prompt(texts)

        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response_text = self._call_api(
                    system_prompt, user_prompt, retry=attempt > 0
                )
                if not response_text or not response_text.strip():
                    last_error = TranslationError("模型回傳空內容（可能 thinking 超過 token 上限）")
                    continue
                return parse_response(response_text, list(texts.keys()))
            except TranslationError as e:
                last_error = e
                continue

        raise last_error or TranslationError("翻譯失敗")

    def _call_api(
        self, system_prompt: str, user_prompt: str, retry: bool = False
    ) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        if retry:
            messages.append({
                "role": "user",
                "content": "Output the JSON object NOW. No thinking, no preamble.",
            })

        payload = {
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.model:
            payload["model"] = self.model

        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=600,
                )
                if resp.status_code != 200:
                    try:
                        err_body = resp.json()
                        err_msg = err_body.get("error", {}).get("message", resp.text)
                    except Exception:
                        err_msg = resp.text
                    if resp.status_code == 429:
                        last_error = TranslationError(f"速率限制: {err_msg}")
                        time.sleep(3 * (attempt + 1))
                        continue
                    raise TranslationError(
                        f"API 錯誤 ({resp.status_code}): {err_msg}"
                    )
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    raise TranslationError("API 回傳空結果")
                return choices[0]["message"]["content"] or ""
            except requests.RequestException as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue

        raise ConnectionError(
            f"重試 {self.max_retries} 次後失敗: {last_error}"
        ) from last_error


# 向後相容別名
LMStudioEngine = LocalModelEngine
OpenAIEngine = LocalModelEngine


# ─── Google Translate (免費公開端點) ───

class GoogleTranslateEngine(TranslationEngine):
    """使用 Google Translate 的免費公開端點 (translate.googleapis.com)。

    不需要 API Key，但有速率限制（大約每秒數個請求）。
    適合大量但格式簡單的文字；複雜格式碼保留能力不如本地 LLM。
    """

    # Minecraft 語言碼 → Google Translate 語言碼
    LANG_MAP = {
        "zh_tw": "zh-TW",
        "zh_cn": "zh-CN",
        "ja_jp": "ja",
        "ko_kr": "ko",
        "es_es": "es",
        "de_de": "de",
        "fr_fr": "fr",
        "it_it": "it",
        "pt_br": "pt",
        "ru_ru": "ru",
        "pl_pl": "pl",
        "th_th": "th",
        "vi_vn": "vi",
    }

    TRANSLATE_URL = "https://translate.googleapis.com/translate_a/single"

    def __init__(self, config: AppConfig) -> None:
        self.max_retries = config.max_retries
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
        })
        # Map Minecraft locale codes used in our config to Google codes
        self._target_lang_code = self.LANG_MAP.get(
            config.target_language, config.target_language
        )

    def check_connection(self) -> bool:
        try:
            result = self._translate_single("test", "zh-TW")
            return bool(result)
        except Exception:
            return False

    def list_models(self) -> list[str]:
        return ["google-translate"]

    def get_loaded_model(self) -> str | None:
        return "Google Translate"

    def translate_batch(
        self, texts: dict[str, str], target_lang: str, mod_name: str
    ) -> dict[str, str]:
        if not texts:
            return {}

        # target_lang passed in is the English name like "Traditional Chinese".
        # We use self._target_lang_code which was set from config.target_language.
        google_lang = self._target_lang_code

        results: dict[str, str] = {}
        for key, source_text in texts.items():
            try:
                translated = self._translate_with_retry(source_text, google_lang)
                if translated:
                    results[key] = translated
            except Exception as e:
                # Skip individual failures; caller will see missing keys
                continue
            # Light rate limiting to avoid 429
            time.sleep(0.05)

        return results

    def _translate_with_retry(self, text: str, target: str) -> str:
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return self._translate_single(text, target)
            except requests.RequestException as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(1 + attempt)
                    continue
        raise TranslationError(f"Google Translate 失敗: {last_error}")

    def _translate_single(self, text: str, target: str) -> str:
        params = {
            "client": "gtx",
            "sl": "en",
            "tl": target,
            "dt": "t",
            "q": text,
        }
        resp = self.session.get(self.TRANSLATE_URL, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(2)
            raise requests.RequestException("rate limit 429")
        resp.raise_for_status()
        data = resp.json()

        # Response shape: [[ [translated, original, ...], [translated, original, ...] ], ...]
        if not data or not isinstance(data, list) or not data[0]:
            return ""
        parts: list[str] = []
        for segment in data[0]:
            if isinstance(segment, list) and len(segment) > 0 and segment[0]:
                parts.append(segment[0])
        return "".join(parts)


# ─── 引擎工廠 ───

PROVIDERS = {
    "local": LocalModelEngine,
    "openai_compat": LocalModelEngine,  # 向後相容
    "google": GoogleTranslateEngine,
}


def create_engine(config: AppConfig) -> TranslationEngine:
    provider = config.api_provider
    engine_cls = PROVIDERS.get(provider, LocalModelEngine)
    return engine_cls(config)
