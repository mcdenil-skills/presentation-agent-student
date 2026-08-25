from collections import defaultdict
from rapidfuzz import fuzz
from tools.pipeline.normalize import normalize


def _write_md(lines, path):
    """Записать собранные строки markdown в файл (utf-8, с финальным переводом строки)."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def verbatim_ok(phrase: str, source_text: str) -> bool:
    """Спот-чек дословности: фраза должна встречаться в исходнике."""
    return normalize(phrase) in normalize(source_text)


def rank_top(items, key, n=5):
    """Топ-N значений key по числу УНИКАЛЬНЫХ людей (по автору), убыванием."""
    people = defaultdict(set)
    count = defaultdict(int)
    for it in items:
        v = (it.get(key) or "").strip()
        if not v:
            continue
        count[v] += 1
        if it.get("автор"):
            people[v].add(it["автор"])
    rows = [{"name": k, "count": count[k], "people": len(people[k])} for k in count]
    rows.sort(key=lambda r: (r["people"], r["count"]), reverse=True)
    return rows[:n]


def group_phrases(items, key, threshold=85):
    """Группирует синонимичные значения key через rapidfuzz. count и people - ДО схлопывания."""
    groups = []
    for it in items:
        v = (it.get(key) or "").strip()
        if not v:
            continue
        nv = normalize(v)
        match = None
        for g in groups:
            if fuzz.token_sort_ratio(nv, g["norm"]) >= threshold:
                match = g
                break
        if match is None:
            match = {"canon": v, "norm": nv, "count": 0, "people": set(), "variants": set()}
            groups.append(match)
        match["count"] += 1
        match["variants"].add(v)
        if it.get("автор"):
            match["people"].add(it["автор"])
    for g in groups:
        g["people"] = len(g["people"])
        g["variants"] = sorted(g["variants"])
    groups.sort(key=lambda g: (g["people"], g["count"]), reverse=True)
    return groups


def write_voice_bank(groups, path):
    lines = ["# Банк голоса (дословно)\n", "| Фраза | Повторов | Уникальных людей |", "|---|---|---|"]
    for g in groups:
        lines.append(f"| {g['canon']} | {g['count']} | {g['people']} |")
    _write_md(lines, path)


def write_top_md(title, top, path):
    lines = [f"# {title}\n", "| # | Название | Повторов | Уникальных людей |", "|---|---|---|---|"]
    for i, r in enumerate(top, 1):
        lines.append(f"| {i} | {r['name']} | {r['count']} | {r['people']} |")
    _write_md(lines, path)


def build_segments(items, top_n=3):
    """Сегмент = пара (job × ниша). Считаем по УНИКАЛЬНЫМ людям, берём топ-N комбинаций."""
    people = defaultdict(set)
    count = defaultdict(int)
    for it in items:
        job = (it.get("job") or "").strip()
        niche = (it.get("ниша") or "").strip()
        if not job or not niche:
            continue
        key = (job, niche)
        count[key] += 1
        if it.get("автор"):
            people[key].add(it["автор"])
    rows = [{"job": k[0], "niche": k[1], "count": count[k], "people": len(people[k])} for k in count]
    rows.sort(key=lambda r: (r["people"], r["count"]), reverse=True)
    return rows[:top_n]


def write_segments(segments, total_people, path):
    """Портреты сегментов с долями + кого ставить в фокус контента."""
    lines = ["# Сегменты ЦА: на кого ориентировать контент\n",
             "| # | Сегмент (хочет × ниша) | Людей | Доля |", "|---|---|---|---|"]
    for i, s in enumerate(segments, 1):
        share = round(100 * s["people"] / total_people) if total_people else 0
        lines.append(f"| {i} | хочет «{s['job']}», ниша: {s['niche']} | {s['people']} | ~{share}% |")
    if segments:
        top = segments[0]
        lines.append(f"\n**Главный фокус:** сегмент «{top['job']} / {top['niche']}» - самый крупный по людям. "
                     f"Контент в первую очередь под него.")
    _write_md(lines, path)


def write_jtbd_verdict(sections, path):
    """sections - список (заголовок, top_list из rank_top). Топ-N по убыванию на языке ЦА."""
    lines = ["# JTBD-вердикт (топ-N по убыванию популярности)\n"]
    for title, top in sections:
        lines.append(f"\n## {title}\n")
        lines.append("| # | Формулировка (язык ЦА) | Повторов | Людей |")
        lines.append("|---|---|---|---|")
        for i, r in enumerate(top, 1):
            lines.append(f"| {i} | {r['name']} | {r['count']} | {r['people']} |")
    _write_md(lines, path)
