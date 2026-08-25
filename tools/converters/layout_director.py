#!/usr/bin/env python3
"""
Режиссёр раскладок: текст ===SLIDE=== -> план сборки для apply_edits.

Главная задача: не «налить текст в один макет», а
ЧЕРЕДОВАТЬ раскладки с ритмом эталона - обложки-разделители, фото+текст,
текстовые тезисы, CTA. Режиссёр:
  1. читает распарсенные слайды (text_to_google.parse_slides);
  2. по типу слайда и наличию брифа ВИЗУАЛ выбирает архетип-раскладку из
     library (knowledge/design/layout-library.json);
  3. ротирует доноров внутри архетипа, чтобы две подряд не были одинаковыми;
  4. собирает JSON-план: add(donor, at:end, set) + delete всех слайдов эталона.

Доноры берутся из ЭТАЛОНА (там зашит дизайн: фон, шрифты, рамки фото, маркеры).
apply_edits дублирует донора и заменяет тексты/фото по ролям. Цветовой акцент
на части заголовка задаётся разметкой [[...]] (см. text_styling).

Использование:
    python layout_director.py deck_SLIDES.txt -o plan.json \\
        [--source ID_эталона] [--title "Название"] [--no-photos]

--no-photos: не назначать фото-доноров (чисто текст/обложки/CTA) - удобно
прогнать сборку без шага подбора картинок. По умолчанию фото-слоты получают
{"brief": "..."} - их заполняет снабженец source_images перед apply_edits.
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from text_to_google import parse_slides

DESIGN_REF = SCRIPT_DIR.parent.parent / "knowledge" / "design"
DEFAULT_LIBRARY = DESIGN_REF / "layout-library.json"
DEFAULT_RHYTHM = DESIGN_REF / "rhythm-pattern.json"

# Тип слайда из ===SLIDE=== -> категория раскладки
COVER_TYPES = {"титульный", "title", "обложка", "раздел", "заключение", "conclusion"}
CTA_TYPES = {"cta", "призыв", "qr", "чат", "chat", "интерактив"}
BULLET_TYPES = {"буллеты", "перечисление"}
PHOTO_TYPES = {"фото", "photo"}
# Урочный слайд-команда: выделенный блок copy-paste. Распознаём ЯВНО, чтобы
# команда с брифом ВИЗУАЛ не улетела в фото-раскладку. Если в эталоне нет
# отдельного донора «команда» - откат на текстовый донор (см. pick_donor).
COMMAND_TYPES = {"команда", "промпт", "command", "prompt"}


def load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_pools(library: dict) -> dict:
    """Группирует архетипы по категориям, сортируя по ходовости (members_count)."""
    pools = {"cover": [], "photo_single": [], "photo_dual": [],
             "text": [], "bullets": [], "cta": [], "command": []}
    for a in library["archetypes"]:
        name = a["name"]
        roles = set(a["roles"])
        has0, has1 = "image:0" in roles, "image:1" in roles
        if name.startswith("обложка") or name == "прочее":
            if roles <= {"title"}:
                pools["cover"].append(a)
        elif name == "фото+текст":
            pools["photo_dual" if has1 else "photo_single"].append(a)
        elif name.startswith("команда"):
            pools["command"].append(a)
        elif name.startswith("текст"):
            pools["text"].append(a)
        elif name.startswith("перечисление"):
            pools["bullets"].append(a)
        elif name.startswith("CTA"):
            pools["cta"].append(a)
    for k in pools:
        pools[k].sort(key=lambda a: -a.get("members_count", 0))
    return pools


def category_for(slide: dict, no_photos: bool) -> str:
    """Категория раскладки по типу слайда и наличию брифа картинки."""
    t = (slide.get("type") or "").lower()
    has_brief = bool(slide.get("visual"))
    if t in COVER_TYPES:
        return "cover"
    if t in COMMAND_TYPES:
        return "command"
    if t in CTA_TYPES:
        return "cta"
    if t in BULLET_TYPES:
        return "bullets"
    if t in PHOTO_TYPES:
        return "text" if no_photos else "photo"
    # обычный контент: бриф ВИЗУАЛ = явное намерение на фото
    if has_brief and not no_photos:
        return "photo"
    return "text"


def has_body(donor: dict) -> bool:
    return "body" in donor.get("roles", [])


import re as _re
_ACCENT = _re.compile(r"\[\[(.+?)\]\]", _re.DOTALL)
_BULLET_PREFIXES = ("- ", "• ", "* ", "– ", "— ", "·  ", "·")


def strip_accent(text: str) -> str:
    """Убирает разметку [[...]], оставляя текст. Для обложек: там фон лаймовый,
    лайм-на-лайме был бы невидим, поэтому акцент на обложках не красим."""
    return _ACCENT.sub(r"\1", text)


def clean_bullets(text: str) -> str:
    """Снимает литеральные маркеры '- '/'• ' в начале строк - у донора свой
    маркер списка, иначе получается двойной (кружок + дефис)."""
    out = []
    for line in text.split("\n"):
        s = line.lstrip()
        for pref in _BULLET_PREFIXES:
            if s.startswith(pref):
                s = s[len(pref):].lstrip()
                break
        out.append(s)
    return "\n".join(out)


def pick_donor(pools: dict, category: str, slide_has_body: bool,
               rotation: dict, prev_donor: int | None,
               body_words: int = 0) -> dict | None:
    """
    Выбирает донора категории с ротацией (round-robin), избегая повтора прошлого
    донора подряд. Категория photo маппится на photo_single. Пустая категория -
    откат на text. Если нужен body, отбрасываем доноров без роли body.

    body_words - сколько слов ляжет в тело слайда. У части доноров текст стоит
    в рамке фиксированного размера (плашка с обводкой): она не растёт, и лишние
    строки вылезают наружу поверх фона. Таким донорам в library проставлен
    max_words - если текст длиннее, донор пропускается (проверено рендером:
    донор #39 при 60+ словах выкидывает две строки за рамку).
    """
    chain = {
        "cover": ["cover", "text"],
        "cta": ["cta", "text"],
        "bullets": ["bullets", "text"],
        # рабочая лошадка эталона - dual #23 (два портрета сбоку, текст рядом
        # не наезжает); 16:9-доноры кладут фото снизу и поджимают буллеты
        "photo": ["photo_dual", "photo_single", "text"],
        # команда: пока нет выделенного донора в эталоне - откат на текст
        # (как фактически у автора в уроке 13а). Появится донор «команда» в
        # library - попадёт в пул command и переключится автоматически.
        "command": ["command", "text", "bullets"],
        "text": ["text", "bullets"],
    }[category]

    candidates = []
    for cat in chain:
        pool = pools.get(cat, [])
        if category != "cover" and slide_has_body:
            pool = [d for d in pool if has_body(d)] or pool
        if body_words:
            # доноры с тесной рамкой отсеиваем, но только если есть замена:
            # пустой пул хуже кривой вёрстки
            roomy = [d for d in pool if body_words <= d.get("max_words", 10 ** 6)]
            pool = roomy or pool
        if pool:
            candidates = pool
            chosen_cat = cat
            break
    else:
        return None

    # round-robin + не повторять прошлого донора
    i = rotation.get(chosen_cat, 0)
    donor = candidates[i % len(candidates)]
    if len(candidates) > 1 and donor["donor"] == prev_donor:
        i += 1
        donor = candidates[i % len(candidates)]
    rotation[chosen_cat] = i + 1
    return donor


def build_set(slide: dict, donor: dict, no_photos: bool, category: str) -> dict:
    """Собирает set ролей: title/body из текста, image:N - бриф картинки."""
    roles = donor.get("roles", [])
    out = {}
    if "title" in roles and slide.get("title"):
        title = slide["title"]
        # на обложках фон лаймовый - акцент не красим (был бы невидим)
        out["title"] = strip_accent(title) if category == "cover" else title
    # тело: обычный текст (ТЕКСТ: -> content) или команда/промпт (ПРОМПТ: -> prompt)
    body_text = slide.get("content") or slide.get("prompt")
    if "body" in roles and body_text:
        out["body"] = clean_bullets(body_text)
    if not no_photos:
        brief = slide.get("visual") or "Тематическое фото в стиле бренда, тёплый свет, без текста"
        ratio = donor.get("ratio_of_image")
        for role in roles:
            if role.startswith("image:"):
                slot = {"brief": brief}
                if ratio:
                    slot["ratio"] = ratio        # снабженцу - ориентация Pexels под рамку
                out[role] = slot
    return out


def split_command_slides(slides: list) -> list:
    """Путь Б: командный слайд, где есть И обвязка (ТЕКСТ), И промпт (ПРОМПТ),
    дробится на ДВА слайда:
      1) текстовый - заголовок + обвязка «зачем» (обычный текст, читается легко);
      2) командный - короткая подводка + сам промпт в тёмной плашке.
    Зачем: у донора-команды одна тёмная плашка, рассчитанная на короткий промпт.
    Если лить туда и обвязку, и промпт - они конкурируют, промпт теряется, длинный
    заголовок наезжает на текст. Разнеся на два слайда, обвязку отдаём текстовому
    донору (он держит 2-строчный заголовок), а плашке - только промпт.
    Команда без обвязки (только ПРОМПТ) не дробится - остаётся одним слайдом."""
    out = []
    for s in slides:
        t = (s.get("type") or "").lower()
        content = (s.get("content") or "").strip()
        prompt = (s.get("prompt") or "").strip()
        if t in COMMAND_TYPES and content and prompt:
            # 1) обвязка -> обычный текстовый слайд (полный заголовок + «зачем»)
            s_text = dict(s)
            s_text["type"] = "контент"
            s_text["prompt"] = None
            s_text["visual"] = None
            out.append(s_text)
            # 2) промпт -> командный слайд с плашкой; короткий заголовок-подводка
            s_cmd = dict(s)
            s_cmd["type"] = "команда"
            s_cmd["title"] = ("Команда в чат Claude:" if prompt.startswith("/")
                              else "Промпт в чат Claude:")
            s_cmd["content"] = None
            s_cmd["visual"] = None
            out.append(s_cmd)
        else:
            out.append(s)
    return out


def direct(slides: list, pools: dict, no_photos: bool) -> list:
    """Назначает раскладку каждому слайду. Возвращает список решений."""
    rotation = {}
    prev_donor = None
    decisions = []
    for s in slides:
        cat = category_for(s, no_photos)
        body_text = s.get("content") or s.get("prompt") or ""
        donor = pick_donor(pools, cat, bool(body_text), rotation, prev_donor,
                           body_words=len(body_text.split()))
        if donor is None:
            decisions.append({"slide": s, "donor": None, "set": {}, "category": cat})
            continue
        st = build_set(s, donor, no_photos, cat)
        decisions.append({
            "slide": s, "donor": donor["donor"], "donor_name": donor["name"],
            "set": st, "category": cat,
        })
        prev_donor = donor["donor"]
    return decisions


def build_plan(decisions: list, source_id: str, title: str, total_etalon: int) -> dict:
    """План для apply_edits: add(at:end) для каждого слайда + удалить эталонные."""
    add = []
    for d in decisions:
        if d["donor"] is None:
            continue
        add.append({"donor": d["donor"], "at": "end", "set": d["set"]})
    plan = {
        "source_id": source_id,
        "title": title,
        "add": add,
        "delete": [{"from": 1, "to": total_etalon}],
    }
    return plan


def report(decisions: list, rhythm: dict):
    """Печатает раскадровку + сверяет ритм с эталоном."""
    n = len(decisions)
    photos = sum(1 for d in decisions if any(k.startswith("image:") for k in d["set"]))
    covers = sum(1 for d in decisions if d["category"] == "cover")
    print(f"\nРаскадровка ({n} слайдов):")
    for i, d in enumerate(decisions, 1):
        title = (d["slide"].get("title") or "")[:46]
        img = " +фото" if any(k.startswith("image:") for k in d["set"]) else ""
        print(f"   {i:>3} [{d['category']:<6}] донор #{d['donor']}{img}  {title}")
    pr = round(photos / n, 2) if n else 0
    et_pr = rhythm.get("photo_ratio")
    print(f"\nРитм: фото {photos}/{n} ({pr}); эталон {et_pr}. Обложек-разделителей: {covers}.")
    if et_pr and pr < et_pr * 0.5:
        print("   ⚠️ фото заметно меньше, чем в эталоне - добавь ВИЗУАЛ: к контентным слайдам.")
    if covers == 0:
        print("   ⚠️ нет обложек-разделителей - пометь секционные слайды ТИП: обложка.")


def main():
    parser = argparse.ArgumentParser(description="Режиссёр раскладок: текст -> план сборки")
    parser.add_argument("input", help="Файл ===SLIDE=== (текст презентации)")
    parser.add_argument("-o", "--out", default="plan.json", help="Файл плана JSON")
    parser.add_argument("--source", default=None, help="ID эталона (по умолчанию из library)")
    parser.add_argument("--title", default="Презентация (сборка)", help="Название копии")
    parser.add_argument("--library", default=str(DEFAULT_LIBRARY))
    parser.add_argument("--rhythm", default=str(DEFAULT_RHYTHM))
    parser.add_argument("--no-photos", action="store_true",
                        help="Не назначать фото-доноров (чистый текст/обложки/CTA)")
    args = parser.parse_args()

    library = load_json(args.library)
    rhythm = load_json(args.rhythm) if Path(args.rhythm).exists() else {}
    source_id = args.source or library.get("etalon_id")
    total_etalon = rhythm.get("total", 50)

    text = Path(args.input).read_text(encoding="utf-8")
    slides = split_command_slides(parse_slides(text))
    pools = build_pools(library)

    decisions = direct(slides, pools, args.no_photos)
    plan = build_plan(decisions, source_id, args.title, total_etalon)
    Path(args.out).write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")

    report(decisions, rhythm)
    print(f"\nПлан сохранён: {args.out}  ({len(plan['add'])} слайдов на сборку)")
    if not args.no_photos and any(
            any(k.startswith("image:") for k in d["set"]) for d in decisions):
        print("Дальше: source_images.py --candidates", args.out,
              "-> выбор фото -> --apply-choices -> apply_edits.py")
    else:
        print("Дальше: apply_edits.py", source_id, args.out, f'"{args.title}"')


if __name__ == "__main__":
    main()
