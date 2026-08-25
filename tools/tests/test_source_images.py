import copy
from source_images import ratio_to_orientation, ratio_to_gen_size
from source_images import brief_to_query, build_gen_prompt
from source_images import collect_briefs
from source_images import write_srcs
from source_images import build_candidates_contact_sheet

def test_ratio_to_orientation():
    assert ratio_to_orientation("16:9") == "landscape"
    assert ratio_to_orientation("4:3") == "landscape"
    assert ratio_to_orientation("1:1") == "square"
    assert ratio_to_orientation("9:16") == "portrait"
    assert ratio_to_orientation("3:4") == "portrait"
    assert ratio_to_orientation("свободное") == "landscape"  # дефолт

def test_ratio_to_gen_size_divisible_by_16():
    for ratio in ("16:9", "4:3", "1:1", "9:16", "3:4"):
        w, h = (int(x) for x in ratio_to_gen_size(ratio).split("x"))
        assert w % 16 == 0 and h % 16 == 0
        assert 1/3 <= w / h <= 3  # ограничение gpt-image-2

def test_ratio_to_gen_size_known():
    assert ratio_to_gen_size("16:9") == "1536x864"
    assert ratio_to_gen_size("1:1") == "1024x1024"
    assert ratio_to_gen_size("9:16") == "864x1536"

def test_ratio_to_gen_size_default_is_valid():
    # неизвестная пропорция -> дефолт; должен быть валиден для gpt-image-2 (÷16, 1:3..3:1)
    assert ratio_to_gen_size("свободное") == "1536x864"
    w, h = (int(x) for x in ratio_to_gen_size("что-угодно").split("x"))
    assert w % 16 == 0 and h % 16 == 0 and 1 / 3 <= w / h <= 3

def test_brief_to_query_trims():
    q = brief_to_query("  уверенный спикер на сцене, тёплый свет, крупный план  ")
    assert q == "уверенный спикер на сцене, тёплый свет, крупный план"

def test_brief_to_query_caps_length():
    long = " ".join(["слово"] * 50)
    q = brief_to_query(long)
    assert len(q.split()) <= 12  # для сток-поиска берём не больше 12 слов

def test_build_gen_prompt_includes_parts():
    p = build_gen_prompt("спикер на сцене", slide_text="Закрытый эфир для своих",
                         brand_style="стиль бренда X")
    assert "спикер на сцене" in p
    assert "стиль бренда X" in p
    assert "без текста" in p.lower() or "no text" in p.lower()

def test_build_gen_prompt_handles_empty_context():
    p = build_gen_prompt("фон-градиент", slide_text="", brand_style="стиль X")
    assert "фон-градиент" in p

PLAN_BRIEFS = {
    "edit": [
        {"slide": 12, "set": {"title": "Заг", "image:0": {"brief": "спикер", "ratio": "16:9"}}},
        {"slide": 20, "set": {"image:0": {"src": "https://already"}}},  # уже src - не бриф
    ],
    "add": [
        {"donor": 30, "after": 5, "set": {"image:1": {"brief": "фон", "ratio": "9:16"}}},
    ],
}

def test_collect_briefs_finds_only_briefs():
    slots = collect_briefs(PLAN_BRIEFS)
    ids = [s["slot_id"] for s in slots]
    assert ids == ["edit:0:image:0", "add:0:image:1"]

def test_collect_briefs_fields():
    slots = collect_briefs(PLAN_BRIEFS)
    s0 = slots[0]
    assert s0 == {"slot_id": "edit:0:image:0", "loc": "edit", "idx": 0,
                  "role": "image:0", "brief": "спикер", "query": "",
                  "ratio": "16:9"}
    s1 = slots[1]
    assert s1["loc"] == "add" and s1["idx"] == 0 and s1["ratio"] == "9:16"

def test_collect_briefs_default_ratio():
    plan = {"edit": [{"slide": 1, "set": {"image:0": {"brief": "x"}}}]}
    slots = collect_briefs(plan)
    assert slots[0]["ratio"] == "свободное"

def test_write_srcs_replaces_brief_with_src():
    plan = copy.deepcopy(PLAN_BRIEFS)
    chosen = {"edit:0:image:0": "https://pexels/p1.jpg", "add:0:image:1": "/tmp/gen_images/g1.png"}
    out = write_srcs(plan, chosen)
    assert out["edit"][0]["set"]["image:0"] == {"src": "https://pexels/p1.jpg"}
    assert out["add"][0]["set"]["image:1"] == {"src": "/tmp/gen_images/g1.png"}
    # текст и уже-src не тронуты
    assert out["edit"][0]["set"]["title"] == "Заг"
    assert out["edit"][1]["set"]["image:0"] == {"src": "https://already"}

def test_write_srcs_ignores_unknown_slot():
    plan = copy.deepcopy(PLAN_BRIEFS)
    out = write_srcs(plan, {"edit:9:image:0": "x"})  # нет такого слота
    assert out["edit"][0]["set"]["image:0"] == {"brief": "спикер", "ratio": "16:9"}

def test_write_srcs_ignores_negative_index():
    plan = copy.deepcopy(PLAN_BRIEFS)
    out = write_srcs(plan, {"edit:-1:image:0": "x"})  # отрицательный индекс не должен писать в [-1]
    assert out["edit"][-1]["set"]["image:0"] == {"src": "https://already"}  # последний слот цел

def test_contact_sheet_shows_slots_and_indexed_candidates():
    data = [
        {"slot_id": "edit:0:image:0", "brief": "спикер", "ratio": "16:9", "candidates": [
            {"kind": "stock", "src": "https://p/1.jpg", "preview": "https://p/1.jpg"},
            {"kind": "gen", "src": "/tmp/g1.png", "preview": "/tmp/g1.png"}]},
    ]
    html = build_candidates_contact_sheet(data, title="Подбор картинок")
    assert "<html" in html.lower()
    assert "edit:0:image:0" in html
    assert "спикер" in html
    assert "https://p/1.jpg" in html
    assert "[0]" in html and "[1]" in html        # индексы для выбора
    assert "stock" in html and "gen" in html

def test_contact_sheet_handles_empty_candidates():
    data = [{"slot_id": "edit:0:image:0", "brief": "x", "ratio": "1:1", "candidates": []}]
    html = build_candidates_contact_sheet(data, title="T")
    assert "<html" in html.lower()
    assert "нет кандидатов" in html
