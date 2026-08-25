from tools.pipeline.normalize import normalize


def test_lowercase_and_trim():
    assert normalize("  Дорого!!!  ") == "дорого"


def test_collapse_repeats():
    assert normalize("оооочень") == "очень"  # 4+ повтора -> 1


def test_yo_to_e():
    assert normalize("дёшево") == "дешево"


def test_strip_punct():
    assert normalize("цена, высокая.") == "цена высокая"
