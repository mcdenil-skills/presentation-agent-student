from tools.pipeline.merge_results import (
    group_phrases, verbatim_ok, rank_top, build_segments, write_voice_bank,
)


def test_group_synonyms():
    items = [{"фраза": "дорого", "ниша": "логистика", "автор": "a"},
             {"фраза": "дороговато", "ниша": "логист", "автор": "b"},
             {"фраза": "цена высокая", "ниша": "логистика", "автор": "c"}]
    groups = group_phrases(items, key="ниша", threshold=80)
    assert any(g["count"] >= 2 for g in groups)


def test_verbatim_substring_check():
    assert verbatim_ok("дорого", "тут есть дорого и ещё") is True
    assert verbatim_ok("дёшево", "тут есть дорого") is False


def test_rank_top_by_unique_people():
    items = [{"ниша": "логистика", "автор": "a"}, {"ниша": "логистика", "автор": "b"},
             {"ниша": "бьюти", "автор": "a"}]
    top = rank_top(items, key="ниша", n=5)
    assert top[0]["name"] == "логистика"
    assert top[0]["people"] == 2


def test_build_segments_intersection():
    items = [{"job": "заработать", "ниша": "логистика", "автор": "a"},
             {"job": "заработать", "ниша": "логистика", "автор": "b"},
             {"job": "создать продукт", "ниша": "бьюти", "автор": "c"}]
    segs = build_segments(items, top_n=3)
    assert segs[0]["job"] == "заработать" and segs[0]["niche"] == "логистика"
    assert segs[0]["people"] == 2


def test_write_voice_bank_creates_file(tmp_path):
    # write_* функции пишут через общий helper _write_md - проверяем, что файл создаётся,
    # в utf-8, с заголовком и строкой таблицы по дословной фразе.
    groups = [{"canon": "дорого для меня", "count": 3, "people": 2}]
    out = tmp_path / "voice-bank.md"
    write_voice_bank(groups, str(out))
    text = out.read_text(encoding="utf-8")
    assert "# Банк голоса (дословно)" in text
    assert "дорого для меня" in text
    assert text.endswith("\n")
