from image_ops import build_image_map, build_replace_image_request, build_create_image_request
from image_ops import drive_public_url, resolve_media_kind, resolve_media

FAKE_PRES = {
    "slides": [
        {"objectId": "s1", "pageElements": [
            {"objectId": "t1", "shape": {"placeholder": {"type": "TITLE"},
                "text": {"textElements": [{"textRun": {"content": "Заголовок\n"}}]}}},
            {"objectId": "img1", "image": {"contentUrl": "http://x"},
                "size": {"width": {"magnitude": 4000000}, "height": {"magnitude": 4000000}},
                "transform": {"translateX": 0, "translateY": 0, "scaleX": 1, "scaleY": 1}},
            {"objectId": "img2", "image": {"contentUrl": "http://y"},
                "size": {"width": {"magnitude": 1600000}, "height": {"magnitude": 900000}},
                "transform": {"translateX": 5000000, "translateY": 0, "scaleX": 1, "scaleY": 1}},
        ]},
        {"objectId": "s2", "pageElements": [
            {"objectId": "t2", "shape": {
                "text": {"textElements": [{"textRun": {"content": "Только текст\n"}}]}}},
        ]},
    ]
}

def test_image_map_numbers_and_slot_roles():
    m = build_image_map(FAKE_PRES)
    assert [s["number"] for s in m] == [1, 2]
    s1 = m[0]
    assert [im["role"] for im in s1["images"]] == ["image:0", "image:1"]
    assert s1["images"][0]["object_id"] == "img1"

def test_image_map_ratio_and_size():
    m = build_image_map(FAKE_PRES)
    s1 = m[0]
    assert s1["images"][0]["ratio"] == "1:1"      # 4000000x4000000
    assert s1["images"][1]["ratio"] == "16:9"     # 1600000x900000
    assert s1["images"][0]["w_emu"] == 4000000

def test_image_map_excludes_text_slides():
    m = build_image_map(FAKE_PRES)
    assert m[1]["images"] == []                    # слайд только с текстом - без слотов


def test_replace_image_request_shape():
    req = build_replace_image_request("img1", "https://x/y.png")
    assert req == {"replaceImage": {
        "imageObjectId": "img1",
        "url": "https://x/y.png",
        "imageReplaceMethod": "CENTER_CROP",
    }}

def test_replace_image_request_custom_method():
    req = build_replace_image_request("img1", "https://x", method="CENTER_INSIDE")
    assert req["replaceImage"]["imageReplaceMethod"] == "CENTER_INSIDE"

def test_create_image_request_shape():
    req = build_create_image_request("p1", "https://x", 100, 200, 300, 400)
    ci = req["createImage"]
    assert ci["url"] == "https://x"
    assert ci["elementProperties"]["pageObjectId"] == "p1"
    assert ci["elementProperties"]["size"]["width"] == {"magnitude": 300, "unit": "EMU"}
    assert ci["elementProperties"]["size"]["height"] == {"magnitude": 400, "unit": "EMU"}
    assert ci["elementProperties"]["transform"]["translateX"] == 100
    assert ci["elementProperties"]["transform"]["translateY"] == 200
    assert ci["elementProperties"]["transform"]["unit"] == "EMU"


def test_drive_public_url():
    assert drive_public_url("ABC123") == "https://drive.google.com/uc?export=download&id=ABC123"


def test_resolve_media_kind():
    assert resolve_media_kind("https://images.unsplash.com/photo-1") == "url"
    assert resolve_media_kind("http://x/y.png") == "url"
    assert resolve_media_kind("/tmp/pic.png") == "local"
    assert resolve_media_kind("photo.jpg") == "local"
    assert resolve_media_kind("1AbCdEfGhIjKlMnOp") == "drive_id"


def test_resolve_media_url_passthrough():
    # http(s) возвращается как есть, drive не трогается (поэтому None безопасен)
    assert resolve_media("https://x/y.png", drive_service=None) == "https://x/y.png"

def test_resolve_media_drive_id():
    assert resolve_media("ABC123", drive_service=None) == \
        "https://drive.google.com/uc?export=download&id=ABC123"
