import json

import pytest

from app.jsonutil import extract_json_object

_OBJ = {"reviewed": [{"index": 0, "score": 8, "reason": "Good"}]}
_JSON = json.dumps(_OBJ)


def test_plain_json():
    assert extract_json_object(_JSON) == _OBJ


def test_fenced_json():
    assert extract_json_object(f"```json\n{_JSON}\n```") == _OBJ


def test_fence_without_language():
    assert extract_json_object(f"```\n{_JSON}\n```") == _OBJ


def test_prose_before_fenced_json():
    raw = f"I verified the claims via web search.\n\nHere are the scores:\n\n```json\n{_JSON}\n```"
    assert extract_json_object(raw) == _OBJ


def test_prose_around_bare_json():
    raw = f"After checking the facts:\n{_JSON}\nLet me know if you need more."
    assert extract_json_object(raw) == _OBJ


def test_no_json_raises():
    with pytest.raises(ValueError, match="No JSON object"):
        extract_json_object("no json here at all")


def test_top_level_array_rejected():
    with pytest.raises(ValueError, match="No JSON object"):
        extract_json_object("[1, 2, 3]")


def test_recovers_json_with_real_newlines_inside_a_string():
    raw = '{"answerMd": "First paragraph.\n\nSecond paragraph."}'
    assert extract_json_object(raw)["answerMd"] == "First paragraph.\n\nSecond paragraph."


def test_recovers_fenced_json_with_real_newlines_inside_a_string():
    raw = '```json\n{"answerMd": "First line.\n\nSecond line."}\n```'
    assert extract_json_object(raw)["answerMd"] == "First line.\n\nSecond line."


def test_keeps_escaped_quotes_intact():
    raw = '{"answerMd": "He said \\"hello\\".\nThen left."}'
    assert extract_json_object(raw)["answerMd"] == 'He said "hello".\nThen left.'
