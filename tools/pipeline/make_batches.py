def make_batches(rows, max_chars=4000):
    """Режет строки на батчи по бюджету символов (прокси токенов). Ничего не теряет."""
    batches, cur, size = [], [], 0
    for r in rows:
        ln = len(r.get("текст", "")) + 20
        if cur and size + ln > max_chars:
            batches.append(cur)
            cur, size = [], 0
        cur.append(r)
        size += ln
    if cur:
        batches.append(cur)
    return batches
