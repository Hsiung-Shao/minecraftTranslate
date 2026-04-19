"""偵測 GPU VRAM 以建議最佳翻譯設定。

使用系統指令查詢，不需要額外 Python 套件：
- NVIDIA: nvidia-smi
- AMD/其他 (Windows): wmic
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass


@dataclass
class GPUInfo:
    name: str
    vram_mb: int


@dataclass
class RecommendedSettings:
    context_tokens: int
    batch_size: int
    max_workers: int
    model_hint: str


def detect_gpu() -> GPUInfo | None:
    """Try NVIDIA first, then AMD/Windows. Return the first GPU found."""
    info = _detect_nvidia()
    if info:
        return info
    info = _detect_windows_wmic()
    if info:
        return info
    return None


def _detect_nvidia() -> GPUInfo | None:
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,name",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode != 0:
            return None
        line = result.stdout.strip().splitlines()[0]
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2:
            return None
        vram_mb = int(parts[0])
        name = parts[1]
        return GPUInfo(name=name, vram_mb=vram_mb)
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, IndexError):
        return None


def _detect_windows_wmic() -> GPUInfo | None:
    try:
        result = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "AdapterRAM,Name"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return None
        lines = [
            l.strip() for l in result.stdout.splitlines()
            if l.strip() and not l.lower().startswith("adapterram")
        ]
        best: GPUInfo | None = None
        for line in lines:
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            try:
                ram_bytes = int(parts[0])
            except ValueError:
                continue
            name = parts[1].strip()
            vram_mb = ram_bytes // (1024 * 1024)
            if best is None or vram_mb > best.vram_mb:
                best = GPUInfo(name=name, vram_mb=vram_mb)
        return best
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def recommend_settings(vram_mb: int) -> RecommendedSettings:
    """根據 VRAM 推薦翻譯設定。"""
    if vram_mb < 6000:
        return RecommendedSettings(
            context_tokens=4096,
            batch_size=8,
            max_workers=1,
            model_hint="建議 4B 模型 (Q4 量化)",
        )
    if vram_mb < 12000:
        return RecommendedSettings(
            context_tokens=8192,
            batch_size=15,
            max_workers=2,
            model_hint="建議 8-9B 模型 (Q4-Q5 量化)",
        )
    if vram_mb < 24000:
        return RecommendedSettings(
            context_tokens=16384,
            batch_size=20,
            max_workers=2,
            model_hint="建議 14B Q5-Q6 或 32B Q3",
        )
    if vram_mb < 48000:
        return RecommendedSettings(
            context_tokens=32768,
            batch_size=30,
            max_workers=3,
            model_hint="建議 32B Q5+ 或 70B Q3",
        )
    return RecommendedSettings(
        context_tokens=65536,
        batch_size=40,
        max_workers=4,
        model_hint="建議 70B+ Q5",
    )
