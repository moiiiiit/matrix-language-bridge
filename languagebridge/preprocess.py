"""Optional profile-specific text preprocessing before translation."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from languagebridge.config import PreprocessConfig

logger = logging.getLogger(__name__)


def _resolve_path(path_str: str) -> Path | None:
    path = Path(path_str)
    candidates = []
    if path.is_absolute():
        candidates.append(path)
    else:
        candidates.append(Path.cwd() / path)
        candidates.append(Path(__file__).resolve().parents[1] / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _load_map(path_str: str) -> dict[str, str]:
    resolved = _resolve_path(path_str)
    if resolved is None:
        raise FileNotFoundError(f"preprocess map not found: {path_str}")
    data = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"preprocess map must be a JSON object: {resolved}")
    return {str(k): str(v) for k, v in data.items()}


def _looks_like_runes(text: str, threshold: float) -> bool:
    chars = [ch for ch in text if not ch.isspace()]
    if not chars:
        return False
    rune_count = sum(1 for ch in chars if 0x16A0 <= ord(ch) <= 0x16FF)
    return (rune_count / len(chars)) >= threshold


def runes_to_phonetic(text: str, cfg: PreprocessConfig) -> tuple[str, bool]:
    if not _looks_like_runes(text, cfg.rune_threshold):
        return text, False

    twin_map = _load_map(cfg.twin_map)
    lone_map = _load_map(cfg.lone_map)

    out: list[str] = []
    i = 0
    while i < len(text):
        rune = text[i]
        if rune == cfg.word_separator:
            out.append(" ")
            i += 1
            continue
        if i + 1 < len(text):
            twin = rune + text[i + 1]
            if twin in twin_map:
                out.append(twin_map[twin])
                i += 2
                continue
        out.append(lone_map.get(rune, rune))
        i += 1

    return "".join(out), True


def apply_preprocess(text: str, cfg: PreprocessConfig | None) -> tuple[str, bool]:
    if cfg is None:
        return text, False
    if cfg.kind != "runes_to_phonetic":
        logger.warning("Unknown preprocess kind '%s'; skipping", cfg.kind)
        return text, False
    try:
        return runes_to_phonetic(text, cfg)
    except Exception as exc:
        logger.warning("Failed preprocessing (%s): %s", cfg.kind, exc)
        return text, False
