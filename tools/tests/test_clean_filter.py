from tools.pipeline.clean_filter import is_noise, clean_rows


def test_greeting_full_match_is_noise():
    assert is_noise("спасибо") is True
    assert is_noise("огонь") is True


def test_signal_word_inside_not_noise():
    assert is_noise("это огонь, окупилось за неделю") is False


def test_short_signal_phrase_survives():
    assert is_noise("дорого!") is False
    assert is_noise("не работает") is False


def test_emoji_only_is_noise():
    assert is_noise("🔥🔥🔥") is True


def test_short_chatter_is_noise():
    assert is_noise("ну да") is True


def test_clean_rows_logs_per_rule():
    rows = [{"текст": "привет"}, {"текст": "дорого!"}, {"текст": "🔥"},
            {"текст": "клиенты уходят к конкурентам"}]
    kept, log = clean_rows(rows, text_key="текст")
    texts = [r["текст"] for r in kept]
    assert "дорого!" in texts
    assert "клиенты уходят к конкурентам" in texts
    assert "привет" not in texts
    assert log["greeting"] >= 1 and log["emoji"] >= 1
    # лог не должен заводить причины вне фиксированного набора правил
    assert set(log.keys()) <= {"empty", "emoji", "greeting", "short"}


def test_empty_and_short_logged():
    # пустая строка -> empty, короткая болтовня без сигнала -> short
    rows = [{"текст": ""}, {"текст": "ну да"}]
    _, log = clean_rows(rows, text_key="текст")
    assert log.get("empty", 0) >= 1
    assert log.get("short", 0) >= 1
