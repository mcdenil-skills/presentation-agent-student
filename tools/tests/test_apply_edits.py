from apply_edits import resolve_plan, build_text_replace_requests, compute_insertion_index

SLIDE_MAP = [
    {"number": 1, "slide_id": "s1", "blocks": [
        {"object_id": "t1", "role": "title", "text": "A"}]},
    {"number": 2, "slide_id": "s2", "blocks": [
        {"object_id": "t2", "role": "title", "text": "B"},
        {"object_id": "b2", "role": "body", "text": "bb"}]},
    {"number": 3, "slide_id": "s3", "blocks": [
        {"object_id": "t3", "role": "title", "text": "C"}]},
    {"number": 4, "slide_id": "s4", "blocks": [
        {"object_id": "t4", "role": "title", "text": "D"}]},
    {"number": 5, "slide_id": "s5", "blocks": [
        {"object_id": "t5", "role": "title", "text": "E"}]},
]


def test_resolve_edit_ok():
    plan = {"edit": [{"slide": 2, "set": {"title": "new", "body": "newb"}}]}
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert errors == []
    assert {"object_id": "t2", "text": "new"} in resolved["edits"]
    assert {"object_id": "b2", "text": "newb"} in resolved["edits"]


def test_resolve_edit_missing_role_errors():
    plan = {"edit": [{"slide": 1, "set": {"body": "x"}}]}
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert any("body" in e for e in errors)
    assert resolved["edits"] == []


def test_resolve_delete_range():
    plan = {"delete": [{"from": 3, "to": 5}, {"slide": 1}]}
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert errors == []
    assert resolved["delete_ids"] == {"s3", "s4", "s5", "s1"}


def test_resolve_add_anchor_in_deleted_errors():
    plan = {"delete": [{"slide": 4}], "add": [{"donor": 2, "after": 4, "set": {}}]}
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert any("after" in e and "4" in e for e in errors)


def test_resolve_move_ok():
    plan = {"move": [{"slide": 5, "after": 1}]}
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert errors == []
    assert {"slide_id": "s5", "after_anchor_id": "s1"} in resolved["moves"]


def test_resolve_missing_slide_errors():
    plan = {"edit": [{"slide": 99, "set": {"title": "x"}}]}
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert any("99" in e for e in errors)


def test_text_replace_requests_structure():
    reqs = build_text_replace_requests("g1", "новый текст")
    assert reqs == [
        {"deleteText": {"objectId": "g1", "textRange": {"type": "ALL"}}},
        {"insertText": {"objectId": "g1", "insertionIndex": 0, "text": "новый текст"}},
    ]


def simulate_move(order, slide_id, j):
    """Имитирует updateSlidesPosition: вставить slide_id перед слайдом,
    что был на индексе j в ИСХОДНОМ порядке (семантика Slides API)."""
    moved = slide_id
    rest = [x for x in order if x != moved]
    if j >= len(order):
        return rest + [moved]
    ref = order[j]
    if ref == moved:
        return order[:]
    pos = rest.index(ref)
    return rest[:pos] + [moved] + rest[pos:]


def test_move_down_lands_right_after_anchor():
    order = ["a", "b", "c", "d", "e"]      # двигаем 'd' после 'b'
    j = compute_insertion_index(order, "b")
    res = simulate_move(order, "d", j)
    assert res.index("d") == res.index("b") + 1


def test_move_up_lands_right_after_anchor():
    order = ["a", "b", "c", "d", "e"]      # двигаем 'b' после 'd'
    j = compute_insertion_index(order, "d")
    res = simulate_move(order, "b", j)
    assert res.index("b") == res.index("d") + 1


def test_move_after_last_anchor_goes_to_end():
    order = ["a", "b", "c"]                # двигаем 'a' после 'c' (последний)
    j = compute_insertion_index(order, "c")
    res = simulate_move(order, "a", j)
    assert res[-1] == "a"


# --- Защита от кривых планов: ошибки собираются, traceback не падает ---

def test_resolve_delete_missing_keys_collected_not_raised():
    plan = {"delete": [{"oops": 1}]}
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert errors  # собрано в errors, а не выброшено KeyError
    assert resolved["delete_ids"] == set()


def test_resolve_delete_reversed_range_errors():
    plan = {"delete": [{"from": 5, "to": 3}]}
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert any("from" in e and "to" in e for e in errors)
    assert resolved["delete_ids"] == set()


def test_resolve_edit_missing_slide_key_collected():
    plan = {"edit": [{"set": {"title": "x"}}]}
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert errors
    assert resolved["edits"] == []


def test_resolve_add_missing_keys_collected():
    plan = {"add": [{"set": {}}]}
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert errors
    assert resolved["adds"] == []


def test_resolve_move_missing_after_collected():
    plan = {"move": [{"slide": 5}]}  # нет 'after'
    resolved, errors = resolve_plan(plan, SLIDE_MAP)
    assert errors
    assert resolved["moves"] == []


# --- Тесты image_map: подмена картинки в edit.set ---

SMAP_IMG = [
    {"number": 12, "slide_id": "s12", "blocks": [
        {"object_id": "t12", "role": "title", "text": "Заг"}]},
]
IMAP = [
    {"number": 12, "slide_id": "s12", "images": [
        {"object_id": "i12a", "role": "image:0", "ratio": "16:9", "w_emu": 1, "h_emu": 1},
        {"object_id": "i12b", "role": "image:1", "ratio": "1:1", "w_emu": 1, "h_emu": 1}]},
]


def test_resolve_image_edit_existing_slot():
    plan = {"edit": [{"slide": 12, "set": {"image:0": {"src": "https://x/y.png"}}}]}
    resolved, errors = resolve_plan(plan, SMAP_IMG, IMAP)
    assert errors == []
    assert resolved["image_edits"] == [{"object_id": "i12a", "src": "https://x/y.png"}]


def test_resolve_image_edit_mixed_with_text():
    plan = {"edit": [{"slide": 12, "set": {"title": "Новый", "image:1": {"src": "/tmp/p.jpg"}}}]}
    resolved, errors = resolve_plan(plan, SMAP_IMG, IMAP)
    assert errors == []
    assert resolved["edits"] == [{"object_id": "t12", "text": "Новый"}]
    assert resolved["image_edits"] == [{"object_id": "i12b", "src": "/tmp/p.jpg"}]


def test_resolve_image_edit_missing_slot_errors():
    plan = {"edit": [{"slide": 12, "set": {"image:5": {"src": "x"}}}]}
    resolved, errors = resolve_plan(plan, SMAP_IMG, IMAP)
    assert any("image:5" in e for e in errors)
    assert resolved["image_edits"] == []


def test_resolve_image_edit_missing_src_errors():
    plan = {"edit": [{"slide": 12, "set": {"image:0": {"ratio": "16:9"}}}]}
    resolved, errors = resolve_plan(plan, SMAP_IMG, IMAP)
    assert any("src" in e for e in errors)


# --- Тесты addImage: добавление новой картинки на слайд ---

ADD_IMG_OK = {"slide": 12, "src": "https://x", "x_emu": 100, "y_emu": 200, "w_emu": 300, "h_emu": 400}


def test_resolve_add_image_ok():
    plan = {"addImage": [ADD_IMG_OK]}
    resolved, errors = resolve_plan(plan, SMAP_IMG, IMAP)
    assert errors == []
    assert resolved["image_adds"] == [
        {"slide_id": "s12", "src": "https://x", "x_emu": 100, "y_emu": 200, "w_emu": 300, "h_emu": 400}]


def test_resolve_add_image_missing_coords_errors():
    plan = {"addImage": [{"slide": 12, "src": "https://x"}]}
    resolved, errors = resolve_plan(plan, SMAP_IMG, IMAP)
    assert any("x_emu" in e or "поля" in e for e in errors)


def test_resolve_add_image_on_deleted_slide_errors():
    plan = {"delete": [{"slide": 12}], "addImage": [ADD_IMG_OK]}
    resolved, errors = resolve_plan(plan, SMAP_IMG, IMAP)
    assert any("addImage" in e and "удаля" in e for e in errors)


# --- Тесты add.set с image:N - валидация против донора ---

def test_resolve_add_set_image_validates_donor_slot():
    # донор #12 имеет image:0 - ок
    plan = {"add": [{"donor": 12, "after": 12, "set": {"image:0": {"src": "https://x"}}}]}
    resolved, errors = resolve_plan(plan, SMAP_IMG, IMAP)
    assert errors == []
    assert resolved["adds"][0]["set"] == {"image:0": {"src": "https://x"}}

def test_resolve_add_set_image_missing_donor_slot_errors():
    # у донора #12 нет image:9
    plan = {"add": [{"donor": 12, "after": 12, "set": {"image:9": {"src": "https://x"}}}]}
    resolved, errors = resolve_plan(plan, SMAP_IMG, IMAP)
    assert any("image:9" in e and "донор" in e for e in errors)

def test_resolve_add_set_image_missing_src_errors():
    plan = {"add": [{"donor": 12, "after": 12, "set": {"image:0": {"ratio": "1:1"}}}]}
    resolved, errors = resolve_plan(plan, SMAP_IMG, IMAP)
    assert any("src" in e for e in errors)
