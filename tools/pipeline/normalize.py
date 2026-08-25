import re


def normalize(text: str) -> str:
    """Нормализация русской фразы для сравнения/дедупа."""
    t = text.lower().replace("ё", "е")
    t = re.sub(r"(.)\1{3,}", r"\1", t)        # 4+ повтора символа -> 1
    t = re.sub(r"[^\w\s]", " ", t)             # пунктуация -> пробел
    t = re.sub(r"\s+", " ", t).strip()
    return t
