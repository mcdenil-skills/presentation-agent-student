#!/usr/bin/env python3
"""
Снабженец картинок: по брифам в плане (image:N -> {"brief": ...}) собирает
кандидатов (стоки Pexels, затем генерация gpt-image-2), показывает контактный
лист, и по выбору вписывает src в план. Дальше ставит apply_edits (часть 2).

Кандидаты не применяются автоматически: владелец сначала выбирает изображение.
"""
from __future__ import annotations

import argparse
import base64
import copy as _copy
import html as _html
import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

# Размер генерации под пропорцию: W и H кратны 16, соотношение в пределах 1:3..3:1
_GEN_SIZE = {
    "16:9": "1536x864", "4:3": "1536x1152", "3:2": "1536x1024", "1:1": "1024x1024",
    "9:16": "864x1536", "3:4": "1152x1536", "2:3": "1024x1536",
}


def ratio_to_orientation(ratio: str) -> str:
    """Пропорция рамки -> ориентация Pexels (landscape/portrait/square)."""
    portrait = {"9:16", "3:4", "2:3"}
    if ratio in portrait:
        return "portrait"
    if ratio == "1:1":
        return "square"
    return "landscape"


def ratio_to_gen_size(ratio: str) -> str:
    """Пропорция рамки -> размер для gpt-image-2 (строка WxH). Дефолт - 16:9."""
    return _GEN_SIZE.get(ratio, "1536x864")


def brief_to_query(brief: str, query: str = "") -> str:
    """Ключевики для сток-поиска. Если у слота задан явный query - берём его:
    сток ищет по английским тегам, а бриф пишется по-русски и описательно
    («две одинаковые мастерские рядом, к левой двери стоит очередь»), поэтому
    поиск по нему выдаёт случайные картинки. Без query - откат на первые слова
    брифа (старое поведение)."""
    if query.strip():
        return query.strip()
    words = brief.strip().split()
    return " ".join(words[:12])


def build_gen_prompt(brief: str, slide_text: str = "", brand_style: str = "") -> str:
    """Промпт для gpt-image-2: бриф + контекст текста слайда + стиль бренда + «без текста».
    По умолчанию картинка БЕЗ текста (текст остаётся родным блоком Slides)."""
    parts = [brief.strip()]
    if slide_text.strip():
        parts.append(f"Контекст слайда: {slide_text.strip()}")
    if brand_style.strip():
        parts.append(brand_style.strip())
    parts.append("Без текста, без надписей, без водяных знаков, без логотипов.")
    return ". ".join(parts)


def collect_briefs(plan: dict) -> list[dict]:
    """Собирает все слоты картинок с брифом (image:N -> {"brief": ...}) из edit и add.
    Слоты с уже готовым src пропускаются."""
    slots = []
    for loc in ("edit", "add"):
        for idx, entry in enumerate(plan.get(loc, [])):
            for role, value in entry.get("set", {}).items():
                if not role.startswith("image:"):
                    continue
                if not isinstance(value, dict) or "brief" not in value:
                    continue
                slots.append({
                    "slot_id": f"{loc}:{idx}:{role}",
                    "loc": loc, "idx": idx, "role": role,
                    "brief": value["brief"],
                    # query - готовый поисковый запрос к стоку (обычно английские
                    # ключевики). Бриф пишется по-русски и описательно - для
                    # генерации это хорошо, а сток по такой фразе выдаёт мусор.
                    "query": value.get("query", ""),
                    "ratio": value.get("ratio", "свободное"),
                })
    return slots


def write_srcs(plan: dict, chosen: dict) -> dict:
    """Возвращает копию плана, где у выбранных слотов бриф заменён на {"src": ...}.
    chosen: {slot_id: src}. Неизвестные slot_id игнорируются."""
    out = _copy.deepcopy(plan)
    for slot_id, src in chosen.items():
        try:
            loc, idx_s, role = slot_id.split(":", 2)
            idx = int(idx_s)
        except ValueError:
            continue
        entries = out.get(loc, [])
        if idx < 0 or idx >= len(entries):
            continue
        if role in entries[idx].get("set", {}):
            entries[idx]["set"][role] = {"src": src}
    return out


def build_candidates_contact_sheet(slots_data: list[dict], title: str = "") -> str:
    """HTML: по слоту - бриф + индексированные кандидаты (превью, источник).
    Индекс [i] нужен, чтобы владелец указал выбор для --apply-choices."""
    blocks = []
    for sd in slots_data:
        if sd["candidates"]:
            cards = []
            for i, c in enumerate(sd["candidates"]):
                prev = _html.escape(c["preview"])
                cards.append(
                    f'<figure><img src="{prev}" alt=""><figcaption>[{i}] '
                    f'{_html.escape(c["kind"])}</figcaption></figure>')
            cand_html = "".join(cards)
        else:
            cand_html = '<div class="empty">нет кандидатов</div>'
        blocks.append(f"""
        <section>
          <h2>{_html.escape(sd['slot_id'])} <small>({_html.escape(sd['ratio'])})</small></h2>
          <p class="brief">{_html.escape(sd['brief'])}</p>
          <div class="cands">{cand_html}</div>
        </section>""")
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>{_html.escape(title)}</title>
<style>
  body {{ font-family:sans-serif; background:#111; color:#eee; padding:24px; }}
  section {{ border-bottom:1px solid #333; padding:12px 0; }}
  .brief {{ color:#9a9; }}
  .cands {{ display:flex; flex-wrap:wrap; gap:12px; }}
  figure {{ margin:0; width:240px; }}
  figure img {{ width:100%; border-radius:6px; display:block; }}
  figcaption {{ font-size:13px; color:#789; }}
  .empty {{ color:#a77; }}
</style></head>
<body><h1>{_html.escape(title)}</h1>{''.join(blocks)}</body></html>"""


def pexels_search(query: str, orientation: str, per_page: int, api_key: str) -> list[str]:
    """Поиск фото на Pexels. Возвращает список прямых URL (src.large)."""
    import requests
    resp = requests.get(
        "https://api.pexels.com/v1/search",
        headers={"Authorization": api_key},
        params={"query": query, "orientation": orientation, "per_page": per_page},
        timeout=30,
    )
    resp.raise_for_status()
    # large2x (~1880px) - чтобы не растягивало на крупных слайдах; large всего 940px
    return [p["src"]["large2x"] for p in resp.json().get("photos", [])]


def generate_image(prompt: str, size: str, api_key: str, out_path: str) -> str:
    """Генерит картинку gpt-image-2, сохраняет в out_path (PNG). Возвращает out_path."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    result = client.images.generate(model="gpt-image-2", prompt=prompt, size=size, n=1)
    b64 = result.data[0].b64_json
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(base64.b64decode(b64))
    return out_path


def read_env(path=".env"):
    """Парсит .env в dict (KEY=VALUE).
    В проекте .env НЕ экспортируется в окружение - читаем файл напрямую."""
    env = {}
    if not os.path.exists(path):
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def _load_keys_and_style():
    """Тянет ключи из .env (read_env), затем os.environ как фоллбэк, brand_style из config."""
    from text_to_google import load_config
    cfg = load_config()
    env = read_env()
    openai_key = env.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
    pexels_key = env.get("PEXELS_API_KEY") or os.environ.get("PEXELS_API_KEY", "")
    return openai_key, pexels_key, cfg.get("brand_style", "")


def gather_candidates(slots, pexels_key, openai_key, brand_style, gen_dir, want_gen):
    """По каждому слоту: стоки Pexels (3), при want_gen - плюс 1 генерёнка. Возвращает slots_data."""
    out = []
    for s in slots:
        cands = []
        try:
            urls = pexels_search(brief_to_query(s["brief"], s.get("query", "")),
                                 ratio_to_orientation(s["ratio"]), 3, pexels_key)
            cands += [{"kind": "stock", "src": u, "preview": u} for u in urls]
        except Exception as e:
            print(f"  Pexels не ответил для {s['slot_id']}: {e}")
        if want_gen and openai_key:
            try:
                prompt = build_gen_prompt(s["brief"], brand_style=brand_style)
                out_path = str(Path(gen_dir) / f"{s['slot_id'].replace(':', '_')}.png")
                generate_image(prompt, ratio_to_gen_size(s["ratio"]), openai_key, out_path)
                cands.append({"kind": "gen", "src": out_path, "preview": out_path})
            except Exception as e:
                print(f"  Генерация не удалась для {s['slot_id']}: {e}")
        out.append({**s, "candidates": cands})
    return out


def main():
    parser = argparse.ArgumentParser(description="Снабженец картинок: кандидаты и запись src в план")
    parser.add_argument("plan", help="JSON-файл плана с брифами")
    parser.add_argument("--candidates", action="store_true", help="Фаза 1: собрать кандидатов + контактный лист")
    parser.add_argument("--gen", action="store_true", help="Добавлять генерёнку к стокам")
    parser.add_argument("--apply-choices", default=None,
                        help="Фаза 2: JSON выбора {slot_id: индекс} -> вписать src в план")
    args = parser.parse_args()

    plan_path = Path(args.plan)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    slots = collect_briefs(plan)

    if args.candidates:
        openai_key, pexels_key, brand_style = _load_keys_and_style()
        gen_dir = plan_path.parent / "gen_images"
        data = gather_candidates(slots, pexels_key, openai_key, brand_style, gen_dir, args.gen)
        cand_path = plan_path.with_name("candidates.json")
        html_path = plan_path.with_name("candidates.html")
        cand_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        html_path.write_text(build_candidates_contact_sheet(data, title=plan_path.stem), encoding="utf-8")
        print(f"Кандидаты: {cand_path}\nКонтактный лист: {html_path}")
        print(f"Слотов: {len(slots)}. Открой контактный лист, выбери индекс [i] по каждому слоту.")
        print('  Собери choices.json, пример: {"edit:0:image:0": 1, "add:0:image:1": 0}')
        return

    if args.apply_choices:
        cand_data = json.loads(plan_path.with_name("candidates.json").read_text(encoding="utf-8"))
        cand_by_slot = {d["slot_id"]: d["candidates"] for d in cand_data}
        choices_idx = json.loads(Path(args.apply_choices).read_text(encoding="utf-8"))
        chosen = {}
        for slot_id, i in choices_idx.items():
            cands = cand_by_slot.get(slot_id, [])
            if 0 <= i < len(cands):
                chosen[slot_id] = cands[i]["src"]
            else:
                print(f"  пропуск {slot_id}: индекс {i} вне диапазона")
        out_plan = write_srcs(plan, chosen)
        out_path = plan_path.with_name(plan_path.stem + ".withsrc.json")
        out_path.write_text(json.dumps(out_plan, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"План с src: {out_path}\nДальше: apply_edits.py <source_id> {out_path}")
        return

    parser.error("укажи --candidates или --apply-choices")


if __name__ == "__main__":
    main()
