from google_to_text import build_slide_map

FAKE_PRES = {
    "slides": [
        {"objectId": "s1", "pageElements": [
            {"objectId": "t1", "shape": {"placeholder": {"type": "TITLE"},
                "text": {"textElements": [{"textRun": {"content": "Заголовок\n"}}]}}},
            {"objectId": "b1", "shape": {"placeholder": {"type": "BODY"},
                "text": {"textElements": [{"textRun": {"content": "Тело\n"}}]}}},
            {"objectId": "img1", "image": {"contentUrl": "http://x"}},
            {"objectId": "x1", "shape": {
                "text": {"textElements": [{"textRun": {"content": "Свободный блок\n"}}]}}},
        ]},
        {"objectId": "s2", "pageElements": [
            {"objectId": "t2", "shape": {"placeholder": {"type": "CENTERED_TITLE"},
                "text": {"textElements": [{"textRun": {"content": "Только тайтл\n"}}]}}},
        ]},
    ]
}


def test_map_numbers_and_ids():
    m = build_slide_map(FAKE_PRES)
    assert [s["number"] for s in m] == [1, 2]
    assert [s["slide_id"] for s in m] == ["s1", "s2"]


def test_roles_unique_and_text_clean():
    m = build_slide_map(FAKE_PRES)
    s1 = m[0]
    roles = {b["role"]: b for b in s1["blocks"]}
    assert roles["title"]["object_id"] == "t1"
    assert roles["title"]["text"] == "Заголовок"
    assert roles["body"]["object_id"] == "b1"
    assert roles["other:0"]["object_id"] == "x1"
    assert roles["other:0"]["text"] == "Свободный блок"


def test_images_not_in_map():
    m = build_slide_map(FAKE_PRES)
    ids = [b["object_id"] for b in m[0]["blocks"]]
    assert "img1" not in ids
    assert len(m[1]["blocks"]) == 1
    assert m[1]["blocks"][0]["role"] == "title"
