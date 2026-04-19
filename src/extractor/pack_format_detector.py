"""自動偵測 Minecraft 版本對應的 pack_format。

優先順序：
1. PrismLauncher / MultiMC: mmc-pack.json (instance 根目錄的 ../)
2. 原生啟動器: version.json
3. Mod JAR 中隨意一個的 pack.mcmeta
4. fallback 到 15 (1.20.1)
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path


# Minecraft version → pack_format (data pack / resource pack shared format after 1.20)
MC_VERSION_TO_PACK_FORMAT: list[tuple[str, int]] = [
    ("1.21.5", 55),
    ("1.21.4", 46),
    ("1.21.2", 42),
    ("1.21.1", 34),
    ("1.21", 34),
    ("1.20.5", 32),
    ("1.20.6", 32),
    ("1.20.3", 22),
    ("1.20.4", 22),
    ("1.20.2", 18),
    ("1.20.1", 15),
    ("1.20", 15),
    ("1.19.4", 13),
    ("1.19.3", 12),
    ("1.19.2", 9),
    ("1.19.1", 9),
    ("1.19", 9),
    ("1.18.2", 8),
    ("1.18.1", 8),
    ("1.18", 8),
    ("1.17.1", 7),
    ("1.17", 7),
    ("1.16.5", 6),
    ("1.16.4", 6),
    ("1.16.3", 6),
    ("1.16.2", 6),
    ("1.16.1", 5),
    ("1.16", 5),
    ("1.15.2", 5),
    ("1.15.1", 5),
    ("1.15", 5),
    ("1.14", 4),
    ("1.13", 4),
]


def version_to_pack_format(mc_version: str) -> int | None:
    for prefix, pf in MC_VERSION_TO_PACK_FORMAT:
        if mc_version.startswith(prefix):
            return pf
    return None


def detect_pack_format(game_dir: Path, mods_folder: Path | None = None) -> tuple[int, str]:
    """Return (pack_format, detection_source).

    Falls back to (15, 'default') if nothing detected.
    """
    # Method 1: PrismLauncher / MultiMC — check ../mmc-pack.json (instance root)
    mc_ver = _from_prismlauncher(game_dir)
    if mc_ver:
        pf = version_to_pack_format(mc_ver)
        if pf is not None:
            return pf, f"PrismLauncher/MultiMC ({mc_ver})"

    # Method 2: vanilla launcher — look for version json in versions/
    mc_ver = _from_vanilla_launcher(game_dir)
    if mc_ver:
        pf = version_to_pack_format(mc_ver)
        if pf is not None:
            return pf, f"version.json ({mc_ver})"

    # Method 3: inspect mod JARs for forge/neoforge manifest
    if mods_folder and mods_folder.is_dir():
        mc_ver = _from_mod_jars(mods_folder)
        if mc_ver:
            pf = version_to_pack_format(mc_ver)
            if pf is not None:
                return pf, f"mod JAR metadata ({mc_ver})"

    return 15, "default (1.20.1)"


def _from_prismlauncher(game_dir: Path) -> str | None:
    # game_dir is usually `<instance>/.minecraft` or `<instance>/minecraft`
    # mmc-pack.json is at the instance root
    for parent in [game_dir.parent, game_dir]:
        mmc_pack = parent / "mmc-pack.json"
        if mmc_pack.is_file():
            try:
                data = json.loads(mmc_pack.read_text(encoding="utf-8"))
                for comp in data.get("components", []):
                    if comp.get("uid") == "net.minecraft":
                        version = comp.get("version")
                        if version:
                            return str(version)
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _from_vanilla_launcher(game_dir: Path) -> str | None:
    versions_dir = game_dir / "versions"
    if not versions_dir.is_dir():
        return None
    # Pick the newest version folder that has a .json
    candidates = []
    for v in versions_dir.iterdir():
        if v.is_dir():
            vjson = v / f"{v.name}.json"
            if vjson.is_file():
                candidates.append(vjson)
    for vjson in candidates:
        try:
            data = json.loads(vjson.read_text(encoding="utf-8"))
            ver = data.get("id") or data.get("assets")
            if ver and isinstance(ver, str) and re.match(r"^1\.\d+", ver):
                return ver
        except (json.JSONDecodeError, OSError):
            continue
    return None


def _from_mod_jars(mods_folder: Path) -> str | None:
    # Try to read mods.toml / fabric.mod.json to find target MC version
    for jar_path in list(mods_folder.glob("*.jar"))[:20]:
        try:
            with zipfile.ZipFile(jar_path, "r") as jar:
                names = set(jar.namelist())
                # Fabric
                if "fabric.mod.json" in names:
                    raw = jar.read("fabric.mod.json").decode("utf-8", errors="replace")
                    try:
                        data = json.loads(raw)
                        depends = data.get("depends", {})
                        mc_ver = depends.get("minecraft")
                        if isinstance(mc_ver, str):
                            extracted = _extract_version(mc_ver)
                            if extracted:
                                return extracted
                    except json.JSONDecodeError:
                        pass
                # Forge / NeoForge
                for toml_path in ("META-INF/mods.toml", "META-INF/neoforge.mods.toml"):
                    if toml_path in names:
                        raw = jar.read(toml_path).decode("utf-8", errors="replace")
                        m = re.search(
                            r'versionRange\s*=\s*"[\[\(](\d+\.\d+(?:\.\d+)?)',
                            raw,
                        )
                        if m:
                            return m.group(1)
        except (zipfile.BadZipFile, OSError, KeyError):
            continue
    return None


def _extract_version(version_range: str) -> str | None:
    """Extract version from fabric dependency string like '>=1.20.1' or '~1.20'."""
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", version_range)
    return m.group(1) if m else None
