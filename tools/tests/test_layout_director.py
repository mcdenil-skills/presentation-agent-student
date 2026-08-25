from tools.converters.layout_director import (
    category_for,
    build_pools,
    pick_donor,
    build_set,
    split_command_slides,
)


# Минимальная library без отдельного донора «команда»
LIBRARY_NO_COMMAND = {
    "archetypes": [
        {"name": "текст (несколько блоков)", "donor": 32,
         "roles": ["title", "body"], "members_count": 6},
        {"name": "фото+текст", "donor": 23,
         "roles": ["title", "body", "image:0", "image:1"], "members_count": 5},
        {"name": "обложка / заголовок", "donor": 11,
         "roles": ["title"], "members_count": 5},
    ],
}

# library, в которой выделенный донор «команда» уже заведён
LIBRARY_WITH_COMMAND = {
    "archetypes": LIBRARY_NO_COMMAND["archetypes"] + [
        {"name": "команда / выделенный блок", "donor": 50,
         "roles": ["title", "body"], "members_count": 3},
    ],
}


def test_command_type_recognized():
    # тип «команда» и «промпт» - своя категория, не «text» и не «photo»
    assert category_for({"type": "команда"}, no_photos=False) == "command"
    assert category_for({"type": "промпт"}, no_photos=False) == "command"


def test_command_with_visual_does_not_leak_to_photo():
    # БАГ-фикс: слайд-команда с брифом ВИЗУАЛ не должен улетать в фото-раскладку
    slide = {"type": "команда", "visual": "скрин терминала"}
    assert category_for(slide, no_photos=False) == "command"


def test_command_falls_back_to_text_without_donor():
    # нет донора «команда» в эталоне - откат на текстовый донор
    pools = build_pools(LIBRARY_NO_COMMAND)
    donor = pick_donor(pools, "command", slide_has_body=True,
                       rotation={}, prev_donor=None)
    assert donor is not None
    assert "body" in donor["roles"]


def test_command_uses_dedicated_donor_when_present():
    # появился донор «команда» в library - команда идёт на него, не на текст
    pools = build_pools(LIBRARY_WITH_COMMAND)
    donor = pick_donor(pools, "command", slide_has_body=True,
                       rotation={}, prev_donor=None)
    assert donor is not None
    assert donor["donor"] == 50


def test_command_prompt_text_goes_to_body():
    # текст команды лежит в поле prompt (из ПРОМПТ:), должен попасть в роль body донора
    donor = {"donor": 51, "roles": ["title", "body"]}
    slide = {"type": "команда", "title": "Установка",
             "prompt": "npx degit anthropics/skills", "content": ""}
    s = build_set(slide, donor, no_photos=True, category="command")
    assert s["title"] == "Установка"
    assert "npx degit" in s["body"]


def test_command_with_body_splits_into_two():
    # Путь Б: команда с обвязкой (content) И промптом дробится на текст + команду
    slides = [{"type": "команда",
               "title": "Шаг 1. Зовём тестировщика - просто словами в чат",
               "content": "Идём в окно чата Claude\nПишем словами, что хотим",
               "prompt": "Напиши тесты на важную функцию и прогони их"}]
    out = split_command_slides(slides)
    assert len(out) == 2
    # 1) обвязка -> текстовый слайд с полным заголовком
    assert out[0]["type"] == "контент"
    assert "окно чата" in out[0]["content"]
    assert not out[0].get("prompt")
    # 2) промпт -> команда с короткой подводкой, без обвязки
    assert out[1]["type"] == "команда"
    assert "Напиши тесты" in out[1]["prompt"]
    assert not out[1].get("content")
    assert out[1]["title"].endswith("чат Claude:")


def test_slash_command_gets_command_label():
    # слэш-команда -> подводка «Команда в чат», промпт словами -> «Промпт в чат»
    slash = split_command_slides([{"type": "команда", "title": "Ревизор",
                                    "content": "обвязка", "prompt": "/code-review"}])
    assert slash[1]["title"].startswith("Команда")
    words = split_command_slides([{"type": "команда", "title": "Тест",
                                   "content": "обвязка", "prompt": "Проверь проект"}])
    assert words[1]["title"].startswith("Промпт")


def test_command_without_body_not_split():
    # команда без обвязки (только промпт) не дробится - остаётся одним слайдом
    out = split_command_slides([{"type": "команда", "title": "Команда",
                                 "prompt": "/code-review", "content": ""}])
    assert len(out) == 1
    assert out[0]["prompt"] == "/code-review"


def test_non_command_slides_untouched():
    # обычные слайды не трогаем
    slides = [{"type": "контент", "title": "А", "content": "текст"},
              {"type": "титульный", "title": "Б"}]
    out = split_command_slides(slides)
    assert out == slides
