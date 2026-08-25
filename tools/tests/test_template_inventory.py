from template_inventory import element_grid_cell, build_layout_signature, signature_key, text_stats, slide_roles, guess_archetype, choose_donor

PAGE_W = 9144000   # стандартный широкий слайд, EMU
PAGE_H = 5143500

def test_grid_cell_left_top():
    el = {"size": {"width": {"magnitude": 1000000}, "height": {"magnitude": 1000000}},
          "transform": {"translateX": 0, "translateY": 0, "scaleX": 1, "scaleY": 1}}
    assert element_grid_cell(el, PAGE_W, PAGE_H) == ("L", "T")

def test_grid_cell_center_middle():
    # центр слайда
    el = {"size": {"width": {"magnitude": 1000000}, "height": {"magnitude": 1000000}},
          "transform": {"translateX": PAGE_W/2 - 500000, "translateY": PAGE_H/2 - 500000,
                        "scaleX": 1, "scaleY": 1}}
    assert element_grid_cell(el, PAGE_W, PAGE_H) == ("C", "M")

def test_grid_cell_right_bottom():
    el = {"size": {"width": {"magnitude": 1000000}, "height": {"magnitude": 1000000}},
          "transform": {"translateX": PAGE_W - 1000000, "translateY": PAGE_H - 1000000,
                        "scaleX": 1, "scaleY": 1}}
    assert element_grid_cell(el, PAGE_W, PAGE_H) == ("R", "B")

def test_grid_cell_missing_geometry_defaults_center():
    assert element_grid_cell({}, PAGE_W, PAGE_H) == ("C", "M")


def _slide_photo_text():
    # фото справа + заголовок + тело с 3 строками
    return {"objectId": "s1", "pageElements": [
        {"objectId": "t", "shape": {"placeholder": {"type": "TITLE"},
            "text": {"textElements": [{"textRun": {"content": "Заголовок\n"}}]}},
            "size": {"width": {"magnitude": 4000000}, "height": {"magnitude": 800000}},
            "transform": {"translateX": 0, "translateY": 0, "scaleX": 1, "scaleY": 1}},
        {"objectId": "b", "shape": {"placeholder": {"type": "BODY"},
            "text": {"textElements": [{"textRun": {"content": "строка1\nстрока2\nстрока3\n"}}]}},
            "size": {"width": {"magnitude": 4000000}, "height": {"magnitude": 2000000}},
            "transform": {"translateX": 0, "translateY": 2500000, "scaleX": 1, "scaleY": 1}},
        {"objectId": "i", "image": {"contentUrl": "http://x"},
            "size": {"width": {"magnitude": 4000000}, "height": {"magnitude": 4000000}},
            "transform": {"translateX": 5000000, "translateY": 600000, "scaleX": 1, "scaleY": 1}},
    ]}


def test_signature_counts_and_bins():
    sig = build_layout_signature(_slide_photo_text(), PAGE_W, PAGE_H)
    assert sig["counts"] == {"text": 2, "image": 1, "table": 0, "line": 0}
    assert sig["image_bins"] == [["R", "M"]]
    # тело имеет 3 строки - бакет "2-4"
    buckets = sorted(b[2] for b in sig["text_bins"])
    assert buckets == ["1", "2-4"]


def test_signature_key_same_layout_different_content():
    s1 = _slide_photo_text()
    s2 = _slide_photo_text()
    # меняем только текст - раскладка та же
    s2["pageElements"][0]["shape"]["text"]["textElements"][0]["textRun"]["content"] = "Другой\n"
    assert signature_key(build_layout_signature(s1, PAGE_W, PAGE_H)) == \
           signature_key(build_layout_signature(s2, PAGE_W, PAGE_H))


def test_signature_key_differs_for_table():
    table_slide = {"objectId": "s9", "pageElements": [
        {"objectId": "tb", "table": {"rows": 4, "columns": 3},
            "size": {"width": {"magnitude": 6000000}, "height": {"magnitude": 3000000}},
            "transform": {"translateX": 1000000, "translateY": 1000000, "scaleX": 1, "scaleY": 1}},
    ]}
    k_tbl = signature_key(build_layout_signature(table_slide, PAGE_W, PAGE_H))
    k_pt = signature_key(build_layout_signature(_slide_photo_text(), PAGE_W, PAGE_H))
    assert k_tbl != k_pt


def test_text_stats_counts_filled_blocks_and_length():
    n_blocks, total_len = text_stats(_slide_photo_text())
    assert n_blocks == 2
    assert total_len > 0


def test_slide_roles_includes_text_image_table():
    roles = slide_roles(_slide_photo_text())
    assert roles == ["title", "body", "image:0"]


def test_slide_roles_table_and_other():
    slide = {"pageElements": [
        {"shape": {"text": {"textElements": [{"textRun": {"content": "Свободный\n"}}]}}},
        {"table": {"rows": 2, "columns": 2}},
    ]}
    assert slide_roles(slide) == ["other:0", "table:0"]


def test_archetype_photo_text():
    sig = build_layout_signature(_slide_photo_text(), PAGE_W, PAGE_H)
    assert guess_archetype(sig, ["Заголовок", "строка1 строка2"]) == "фото+текст"


def test_archetype_table():
    sig = {"counts": {"text": 1, "image": 0, "table": 1, "line": 0},
           "text_bins": [["C", "T", "1"]], "image_bins": [], "table_dims": ["4x3"], "layout_id": None}
    assert guess_archetype(sig, ["Прайс"]) == "таблица 4x3"


def test_archetype_bullets():
    sig = {"counts": {"text": 2, "image": 0, "table": 0, "line": 0},
           "text_bins": [["C", "T", "1"], ["L", "M", "5+"]], "image_bins": [], "table_dims": [], "layout_id": None}
    assert guess_archetype(sig, ["Заголовок", "a\nb\nc\nd\ne\nf"]) == "перечисление (буллеты)"


def test_archetype_cta_by_keyword():
    sig = build_layout_signature(_slide_photo_text(), PAGE_W, PAGE_H)
    # ключевое слово про чат перебивает обычное имя
    assert guess_archetype(sig, ["Переходи в чат", "ссылка"]) == "CTA / призыв в чат"


def test_archetype_cover():
    sig = {"counts": {"text": 1, "image": 0, "table": 0, "line": 0},
           "text_bins": [["C", "M", "1"]], "image_bins": [], "table_dims": [], "layout_id": None}
    assert guess_archetype(sig, ["Новая система контента"]) == "обложка / заголовок"


def test_choose_donor_picks_most_filled():
    members = [
        {"number": 3, "n_blocks": 1, "text_len": 10},
        {"number": 5, "n_blocks": 2, "text_len": 80},   # самый полный
        {"number": 8, "n_blocks": 2, "text_len": 40},
    ]
    assert choose_donor(members)["number"] == 5

def test_choose_donor_tiebreak_lowest_number():
    members = [
        {"number": 9, "n_blocks": 2, "text_len": 50},
        {"number": 4, "n_blocks": 2, "text_len": 50},   # та же полнота - меньший номер
    ]
    assert choose_donor(members)["number"] == 4


from template_inventory import cluster_slides

def _pres_with_repeats():
    # 3 слайда «фото+текст» (повторы раскладки) + 1 таблица -> 2 кластера
    s_pt = _slide_photo_text
    a, b, c = s_pt(), s_pt(), s_pt()
    a["objectId"], b["objectId"], c["objectId"] = "a", "b", "c"
    # у b больше текста - должен стать донором
    b["pageElements"][1]["shape"]["text"]["textElements"][0]["textRun"]["content"] = \
        "длинная\nстрока\nтекста\nещё\n"
    table_slide = {"objectId": "tb", "pageElements": [
        {"table": {"rows": 4, "columns": 3},
            "size": {"width": {"magnitude": 6000000}, "height": {"magnitude": 3000000}},
            "transform": {"translateX": 1000000, "translateY": 1000000, "scaleX": 1, "scaleY": 1}},
        {"shape": {"placeholder": {"type": "TITLE"},
            "text": {"textElements": [{"textRun": {"content": "Прайс\n"}}]}},
            "size": {"width": {"magnitude": 4000000}, "height": {"magnitude": 700000}},
            "transform": {"translateX": 0, "translateY": 0, "scaleX": 1, "scaleY": 1}},
    ]}
    return {"slides": [a, b, c, table_slide]}

def test_cluster_collapses_repeats():
    clusters = cluster_slides(_pres_with_repeats())
    assert len(clusters) == 2

def test_cluster_donor_and_members():
    clusters = cluster_slides(_pres_with_repeats())
    photo = [c for c in clusters if c["archetype_guess"] == "фото+текст"][0]
    assert sorted(photo["members"]) == [1, 2, 3]
    assert photo["donor"] == 2            # слайд b - самый полный
    assert photo["donor_slide_id"] == "b"
    assert "image:0" in photo["roles"]

def test_cluster_sorted_by_size_desc():
    clusters = cluster_slides(_pres_with_repeats())
    sizes = [len(c["members"]) for c in clusters]
    assert sizes == sorted(sizes, reverse=True)


from template_inventory import ratio_label, build_palette, build_contact_sheet_html

def test_ratio_label_common():
    assert ratio_label(1600, 900) == "16:9"
    assert ratio_label(1000, 1000) == "1:1"
    assert ratio_label(900, 1600) == "9:16"

def test_build_palette_shape():
    clusters = cluster_slides(_pres_with_repeats())
    palette = build_palette(clusters, source_id="SRC123")
    assert palette["source_id"] == "SRC123"
    arche = palette["archetypes"]
    assert isinstance(arche, list) and len(arche) == 2
    photo = [a for a in arche if a["name"] == "фото+текст"][0]
    assert photo["donor"] == 2
    assert photo["roles"] == ["title", "body", "image:0"]
    assert photo["ratio_of_image"] == "1:1"   # картинка в фикстуре 4000000x4000000
    # у таблицы нет картинки -> поля ratio_of_image нет
    table = [a for a in arche if a["name"].startswith("таблица")][0]
    assert "ratio_of_image" not in table
    # служебное поле _donor_slide не утекает в JSON-палитру
    assert "_donor_slide" not in photo


def test_contact_sheet_html_contains_cards():
    clusters = cluster_slides(_pres_with_repeats())
    thumbs = {2: "http://thumb/2", 4: "http://thumb/4"}  # по номеру донора
    html = build_contact_sheet_html(clusters, thumbs, title="Новая система контента")
    assert "<html" in html.lower()
    assert "фото+текст" in html
    assert "http://thumb/2" in html          # превью донора-картинки
    assert "слайдов: 3" in html              # размер кластера фото+текст
    assert "донор #2" in html

def test_contact_sheet_handles_missing_thumb():
    clusters = cluster_slides(_pres_with_repeats())
    html = build_contact_sheet_html(clusters, {}, title="X")  # нет превью
    assert "<html" in html.lower()           # не падает без превью


from template_inventory import filter_clusters

def test_filter_clusters_by_min_count():
    clusters = cluster_slides(_pres_with_repeats())  # размеры [3, 1]: фото+текст x3, таблица x1
    keep = filter_clusters(clusters, 3)
    assert [c["archetype_guess"] for c in keep] == ["фото+текст"]   # таблица (1 повтор) отброшена
    assert filter_clusters(clusters, 1) == clusters                # при пороге 1 ничего не теряем
    assert filter_clusters(clusters, 99) == []                     # порог выше всех - пусто
