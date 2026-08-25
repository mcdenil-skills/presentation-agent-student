from tools.pipeline.make_batches import make_batches


def test_splits_by_token_budget():
    rows = [{"текст": "ф" * 40, "автор": f"a{i}", "лист": "l", "строка": i} for i in range(50)]
    batches = make_batches(rows, max_chars=400)
    assert len(batches) > 1
    assert all("автор" in r for b in batches for r in b)


def test_no_row_lost():
    rows = [{"текст": "abc", "автор": "x", "лист": "l", "строка": i} for i in range(10)]
    batches = make_batches(rows, max_chars=20)
    assert sum(len(b) for b in batches) == 10
