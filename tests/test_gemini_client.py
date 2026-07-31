from types import SimpleNamespace

import pytest

from app.clients.gemini import extract_text


def _response(parts, finish_reason="STOP"):
    content = SimpleNamespace(parts=parts)
    return SimpleNamespace(
        candidates=[SimpleNamespace(content=content, finish_reason=finish_reason)]
    )


def _part(text, thought=False):
    return SimpleNamespace(text=text, thought=thought)


def test_joins_the_answer_parts():
    assert extract_text(_response([_part("First. "), _part("Second.")])) == "First. Second."


def test_skips_thought_parts():
    # `response.text` returns None for this shape, which is what made a good
    # answer look like an empty one.
    response = _response([_part("thinking out loud", thought=True), _part("The answer.")])
    assert extract_text(response) == "The answer."


def test_survives_parts_without_a_thought_flag():
    assert extract_text(_response([SimpleNamespace(text="Plain.")])) == "Plain."


def test_ignores_non_text_parts():
    response = _response([SimpleNamespace(inline_data=b"..."), _part("Text.")])
    assert extract_text(response) == "Text."


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(candidates=[]),
        SimpleNamespace(candidates=[SimpleNamespace(content=None, finish_reason="SAFETY")]),
        SimpleNamespace(
            candidates=[
                SimpleNamespace(content=SimpleNamespace(parts=None), finish_reason="MAX_TOKENS")
            ]
        ),
    ],
)
def test_returns_empty_for_a_candidate_with_nothing_in_it(response):
    assert extract_text(response) == ""
