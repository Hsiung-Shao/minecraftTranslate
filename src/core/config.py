from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class AppConfig:
    api_provider: str = "local"
    api_url: str = "http://26.82.236.63:1234/v1"
    api_key: str = ""
    api_model: str = ""
    target_language: str = "zh_tw"
    mods_folder: str = ""
    output_folder: str = ""
    resource_pack_name: str = "ModTranslation"
    pack_format: int = 15
    batch_size: int = 10
    temperature: float = 0.1
    max_retries: int = 3
    cache_db_path: str = "translation_cache.db"
    theme: str = "dark"
    max_workers: int = 2
    context_tokens: int = 8192
    reserved_tokens: int = 2048
    log_folder: str = "logs"
    enable_file_log: bool = True

    @classmethod
    def load(cls, path: Path) -> AppConfig:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
            filtered = {k: v for k, v in data.items() if k in valid_fields}
            return cls(**filtered)
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2, ensure_ascii=False)
