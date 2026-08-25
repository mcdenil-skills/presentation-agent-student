#!/usr/bin/env python3
"""
Анализатор стиля презентации — снимает «как сделано красиво» в цифрах.

Зачем: чтобы воспроизводить дизайн эталона, агенту нужны точные значения, а не
«на глаз»: какой именно HEX у лаймового акцента, какими шрифтами и кеглями
набраны заголовки и тело, какого цвета фон, какие рамки у фото. Скрипт читает
презентацию через API и выдаёт это как JSON + человекочитаемую сводку.

Использование:
    python extract_style.py "URL_или_ID" [-o style.json]

Переиспользует: get_credentials (text_to_google), read_presentation
(template_inventory), build_image_map (image_ops).
"""

from __future__ import annotations

import sys
import json
import argparse
from pathlib import Path
from collections import Counter, defaultdict

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from googleapiclient.discovery import build
except ImportError:
    print("❌ Нет googleapiclient. pip install google-api-python-client google-auth")
    sys.exit(1)

from text_to_google import get_credentials
from google_to_text import extract_presentation_id
from template_inventory import read_presentation
from image_ops import build_image_map


def rgb_to_hex(rgb: dict) -> str:
    """{red,green,blue} (0..1, нули могут отсутствовать) -> '#RRGGBB'."""
    r = round(rgb.get("red", 0) * 255)
    g = round(rgb.get("green", 0) * 255)
    b = round(rgb.get("blue", 0) * 255)
    return f"#{r:02X}{g:02X}{b:02X}"


def build_color_scheme(presentation: dict) -> dict:
    """Карта themeColor-тип -> HEX из colorScheme мастеров/лейаутов."""
    scheme = {}
    pages = (presentation.get("masters", []) or []) + (presentation.get("layouts", []) or [])
    for page in pages:
        cs = page.get("pageProperties", {}).get("colorScheme", {})
        for c in cs.get("colors", []):
            t = c.get("type")
            rgb = c.get("color", {}).get("rgbColor", {})
            if t and t not in scheme:
                scheme[t] = rgb_to_hex(rgb)
    return scheme


def resolve_color(opaque: dict, scheme: dict) -> str | None:
    """opaqueColor -> HEX. Тема резолвится через scheme."""
    if not opaque:
        return None
    if "rgbColor" in opaque:
        return rgb_to_hex(opaque["rgbColor"])
    theme = opaque.get("themeColor")
    if theme:
        return scheme.get(theme, f"theme:{theme}")
    return None


def placeholder_kind(el: dict) -> str:
    """TITLE / BODY / SUBTITLE / other — по типу плейсхолдера shape."""
    ph = el.get("shape", {}).get("placeholder", {})
    return ph.get("type") or "other"


def analyze(presentation: dict) -> dict:
    scheme = build_color_scheme(presentation)

    # стили текста, сгруппированные по роли плейсхолдера
    by_kind = defaultdict(lambda: {
        "fonts": Counter(), "sizes": Counter(), "colors": Counter(), "bold": Counter()
    })
    bg = Counter()

    for slide in presentation.get("slides", []):
        # фон слайда
        fill = slide.get("slideProperties", {})  # на случай иной структуры
        page_fill = slide.get("pageProperties", {}).get("pageBackgroundFill", {})
        if "solidFill" in page_fill:
            hexv = resolve_color(page_fill["solidFill"].get("color", {}), scheme)
            bg[hexv or "?"] += 1
        elif "stretchedPictureFill" in page_fill:
            bg["picture"] += 1
        else:
            bg["inherited"] += 1

        for el in slide.get("pageElements", []):
            shape = el.get("shape")
            if not shape:
                continue
            kind = placeholder_kind(el)
            text = shape.get("text", {})
            for te in text.get("textElements", []):
                tr = te.get("textRun")
                if not tr:
                    continue
                content = tr.get("content", "")
                if not content.strip():
                    continue
                st = tr.get("style", {})
                font = st.get("fontFamily")
                if font:
                    by_kind[kind]["fonts"][font] += 1
                size = st.get("fontSize", {}).get("magnitude")
                if size:
                    by_kind[kind]["sizes"][round(size)] += 1
                col = resolve_color(
                    st.get("foregroundColor", {}).get("opaqueColor", {}), scheme)
                if col:
                    by_kind[kind]["colors"][col] += 1
                by_kind[kind]["bold"][bool(st.get("bold"))] += 1

    # рамки фото: уникальные пропорции + размеры
    image_map = build_image_map(presentation)
    frame_counter = Counter()
    for s in image_map:
        for img in s["images"]:
            frame_counter[(img["role"], img["ratio"])] += 1

    def top(counter, n=8):
        return [{"value": str(k), "count": v} for k, v in counter.most_common(n)]

    result = {
        "color_scheme": scheme,
        "backgrounds": top(bg),
        "text_styles": {
            kind: {
                "fonts": top(d["fonts"]),
                "sizes_pt": top(d["sizes"]),
                "colors": top(d["colors"]),
                "bold": {str(k): v for k, v in d["bold"].items()},
            }
            for kind, d in by_kind.items()
        },
        "image_frames": [{"role_ratio": str(k), "count": v}
                         for k, v in frame_counter.most_common()],
    }
    return result


def greenish(hexv: str) -> bool:
    """Эвристика на лайм: зелёный канал доминирует, синий низкий."""
    if not hexv.startswith("#") or len(hexv) != 7:
        return False
    r, g, b = int(hexv[1:3], 16), int(hexv[3:5], 16), int(hexv[5:7], 16)
    return g > 180 and g > r and b < 120


def main():
    parser = argparse.ArgumentParser(description="Снять стиль презентации в JSON")
    parser.add_argument("presentation", help="URL или ID")
    parser.add_argument("-o", "--out", default=None, help="JSON-файл (по умолчанию style.json)")
    args = parser.parse_args()

    pid = extract_presentation_id(args.presentation)
    credentials = get_credentials()
    slides_service = build("slides", "v1", credentials=credentials)
    print("Загружаю презентацию...")
    presentation = read_presentation(slides_service, pid)

    style = analyze(presentation)
    out = args.out or "style.json"
    Path(out).write_text(json.dumps(style, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nСтиль сохранён: {out}\n")
    print("Цветовая схема (тема):")
    for t, h in style["color_scheme"].items():
        mark = "  <- лайм?" if greenish(h) else ""
        print(f"   {t:<10} {h}{mark}")
    print("\nФоны слайдов:", ", ".join(f"{b['value']}×{b['count']}" for b in style["backgrounds"]))
    for kind, d in style["text_styles"].items():
        print(f"\n[{kind}]")
        print("   шрифты:", ", ".join(f"{x['value']}×{x['count']}" for x in d["fonts"][:4]))
        print("   кегли:", ", ".join(f"{x['value']}pt×{x['count']}" for x in d["sizes_pt"][:5]))
        limes = [c for c in d["colors"] if greenish(c["value"])]
        print("   цвета:", ", ".join(f"{x['value']}×{x['count']}" for x in d["colors"][:6]))
        if limes:
            print("   лайм среди цветов:", ", ".join(f"{x['value']}×{x['count']}" for x in limes))
    print("\nРамки фото (роль/пропорция):",
          ", ".join(f"{x['role_ratio']}×{x['count']}" for x in style["image_frames"]))


if __name__ == "__main__":
    main()
