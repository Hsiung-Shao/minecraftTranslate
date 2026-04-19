from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


class CacheStore:
    def __init__(self, db_path: Path | str) -> None:
        self._db_path = str(db_path)
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS translations (
                source_text TEXT NOT NULL,
                target_lang TEXT NOT NULL,
                translated_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (source_text, target_lang)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_lang
            ON translations(target_lang)
        """)
        conn.commit()

    def get(self, source_text: str, target_lang: str) -> str | None:
        conn = self._get_conn()
        cursor = conn.execute(
            "SELECT translated_text FROM translations WHERE source_text = ? AND target_lang = ?",
            (source_text, target_lang),
        )
        row = cursor.fetchone()
        return row[0] if row else None

    def put(self, source_text: str, target_lang: str, translated_text: str) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT INTO translations (source_text, target_lang, translated_text)
            VALUES (?, ?, ?)
            ON CONFLICT (source_text, target_lang)
            DO UPDATE SET translated_text = excluded.translated_text,
                          updated_at = CURRENT_TIMESTAMP
            """,
            (source_text, target_lang, translated_text),
        )
        conn.commit()

    def get_batch(
        self, keys: list[tuple[str, str]]
    ) -> dict[tuple[str, str], str]:
        if not keys:
            return {}
        conn = self._get_conn()
        results: dict[tuple[str, str], str] = {}

        chunk_size = 200
        for i in range(0, len(keys), chunk_size):
            chunk = keys[i : i + chunk_size]
            placeholders = " OR ".join(
                ["(source_text = ? AND target_lang = ?)"] * len(chunk)
            )
            params = [v for k in chunk for v in k]
            cursor = conn.execute(
                f"SELECT source_text, target_lang, translated_text "
                f"FROM translations WHERE {placeholders}",
                params,
            )
            for row in cursor.fetchall():
                results[(row[0], row[1])] = row[2]

        return results

    def put_batch(self, entries: list[tuple[str, str, str]]) -> None:
        if not entries:
            return
        conn = self._get_conn()
        conn.executemany(
            """
            INSERT INTO translations (source_text, target_lang, translated_text)
            VALUES (?, ?, ?)
            ON CONFLICT (source_text, target_lang)
            DO UPDATE SET translated_text = excluded.translated_text,
                          updated_at = CURRENT_TIMESTAMP
            """,
            entries,
        )
        conn.commit()

    def get_stats(self) -> dict[str, int]:
        conn = self._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM translations")
        total = cursor.fetchone()[0]
        cursor = conn.execute(
            "SELECT target_lang, COUNT(*) FROM translations GROUP BY target_lang"
        )
        by_lang = {row[0]: row[1] for row in cursor.fetchall()}
        return {"total": total, "by_language": by_lang}

    def close(self) -> None:
        if hasattr(self._local, "conn") and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None
