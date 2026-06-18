from src.prompts import MESSAGE_WRITER_PROMPT


def test_writer_prompt_contains_deskia_name():
    assert "Deskia" in MESSAGE_WRITER_PROMPT


def test_writer_prompt_has_all_template_variables():
    assert "{message_category}" in MESSAGE_WRITER_PROMPT
    assert "{message_content}" in MESSAGE_WRITER_PROMPT
    assert "{is_first_message}" in MESSAGE_WRITER_PROMPT


def test_writer_prompt_forbids_other_ai_brands():
    upper = MESSAGE_WRITER_PROMPT.upper()
    assert "NEVER IDENTIFY" in upper or "NOT CLAUDE" in upper or "DO NOT IDENTIFY" in upper
