import re
from collections import Counter
from tools.lexicon import NOISE_PATTERNS, GREETING_WORDS, SIGNAL_WORDS, MIN_MESSAGE_LENGTH
from tools.pipeline.normalize import normalize

_NOISE_RE = [re.compile(p, re.IGNORECASE) for p in NOISE_PATTERNS]


def _has_signal(norm: str) -> bool:
    return any(s in norm for s in SIGNAL_WORDS)


def _classify(message: str):
    """Причина отсева (`empty`/`emoji`/`greeting`/`short`) или None, если фраза осмысленная.
    ЕДИНЫЙ источник правды: на нём построены is_noise и clean_rows - правила не разойдутся."""
    msg = (message or "").strip()
    if not msg:
        return "empty"
    if any(rx.match(msg) for rx in _NOISE_RE):
        return "emoji"
    norm = normalize(msg)
    if not norm:
        return "empty"
    if norm in GREETING_WORDS:
        return "greeting"
    if _has_signal(norm):                  # сигнальное слово спасает от среза по длине
        return None
    text_only = re.sub(r"[^\w\s]", "", msg)
    text_only = re.sub(r"\s+", " ", text_only).strip()
    if len(text_only) < MIN_MESSAGE_LENGTH:
        return "short"
    return None


def is_noise(message: str) -> bool:
    return _classify(message) is not None


def clean_rows(rows, text_key="текст"):
    """Возвращает (оставшиеся_строки, лог_по_правилам Counter->dict)."""
    kept, log = [], Counter()
    for r in rows:
        reason = _classify(r.get(text_key))
        if reason:
            log[reason] += 1
        else:
            kept.append(r)
    return kept, dict(log)
