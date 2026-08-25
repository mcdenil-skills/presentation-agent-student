from tools.converters.text_to_google import SLIDE_TYPE_MAP


def test_command_alias_maps_to_prompt_template():
    # тип «команда» для уроков рендерится тем же выделенным шаблоном, что и «промпт»
    assert SLIDE_TYPE_MAP['команда'] == SLIDE_TYPE_MAP['промпт']
