from unittest.mock import AsyncMock

import pytest

from app.errors import TruncatedOutputError
from app.services.answer_text import (
    MAX_ANSWER_LEN,
    drop_incomplete_tail,
    ends_on_complete_sentence,
    enforce_length,
    sanitize_answer,
    trim_to_sentence,
)


def test_sanitize_strips_cite_tags_but_keeps_the_prose():
    raw = (
        'The singularity is a long-theorized moment. <cite index="4-2">It refers to the point '
        "at which AI outpaces human intelligence.</cite> The classic version is recursive."
    )
    cleaned = sanitize_answer(raw)
    assert "<cite" not in cleaned
    assert "</cite>" not in cleaned
    assert "It refers to the point at which AI outpaces human intelligence." in cleaned


def test_sanitize_strips_web_search_source_links():
    raw = (
        "Altman called it the singularity "
        "([tomshardware.com](https://www.tomshardware.com/tech-industry/x)). "
        "Experts disagree."
    )
    assert sanitize_answer(raw) == "Altman called it the singularity. Experts disagree."


def test_sanitize_strips_a_multi_source_citation_group():
    raw = "It happened ([a.com](https://a.com/x), [b.org](https://b.org/y)). Next."
    assert sanitize_answer(raw) == "It happened. Next."


def test_sanitize_keeps_a_real_prose_link():
    raw = "Read [the announcement](https://openai.com/news) for details."
    assert sanitize_answer(raw) == raw


def test_sanitize_converts_literal_slash_n_to_paragraph_break():
    cleaned = sanitize_answer("First paragraph. /n Second paragraph.")
    assert "/n" not in cleaned
    assert cleaned == "First paragraph.\n\nSecond paragraph."


def test_sanitize_leaves_urls_containing_slash_n_alone():
    cleaned = sanitize_answer("See https://example.com/news for more.")
    assert "https://example.com/news" in cleaned


def test_sanitize_leaves_a_bare_path_starting_with_n_alone():
    assert sanitize_answer("Open the /notes page.") == "Open the /notes page."
    assert sanitize_answer("/news is the section.") == "/news is the section."


def test_sanitize_does_not_touch_punctuation_spacing_in_clean_prose():
    # No citation was removed, so nothing licenses editing the spacing.
    text = "What is a token ? Nobody knows."
    assert sanitize_answer(text) == text


def test_sanitize_converts_escaped_newlines_and_br_tags():
    assert sanitize_answer("One.\\n\\nTwo.") == "One.\n\nTwo."
    assert sanitize_answer("One.<br><br>Two.") == "One.\n\nTwo."


def test_sanitize_collapses_extra_blank_lines():
    assert sanitize_answer("One.\n\n\n\nTwo.") == "One.\n\nTwo."


def test_trim_drops_whole_sentences_never_half_of_one():
    sentences = "This is a complete sentence about models. " * 40
    trimmed = trim_to_sentence(sentences, MAX_ANSWER_LEN)
    assert len(trimmed) <= MAX_ANSWER_LEN
    assert trimmed.endswith(".")


def test_trim_closes_a_dangling_bold_marker():
    # The closing ** lives in a sentence that gets dropped, leaving the opener
    # stranded in the kept text.
    text = "A **bold run starts here. " + "A fine sentence. " * 70 + "and ends here**."
    trimmed = trim_to_sentence(text, MAX_ANSWER_LEN)
    assert trimmed.count("**") % 2 == 0


def test_trim_marks_a_single_oversized_sentence_as_cut():
    trimmed = trim_to_sentence("word " * 500, 100)
    assert len(trimmed) <= 100
    assert trimmed.endswith("…")


async def test_enforce_length_returns_short_answers_untouched():
    revise = AsyncMock()
    assert await enforce_length("Short answer.", revise) == "Short answer."
    revise.assert_not_called()


async def test_enforce_length_revises_rather_than_truncating():
    long_answer = "A sentence that says something. " * 50
    revise = AsyncMock(return_value="A properly rewritten, complete answer.")

    result = await enforce_length(long_answer, revise)

    assert result == "A properly rewritten, complete answer."
    assert revise.call_count == 1


async def test_enforce_length_retries_with_a_tighter_target():
    long_answer = "A sentence that says something. " * 50
    revise = AsyncMock(
        side_effect=[
            "Still far too long. " * 60,
            "Short enough this time.",
        ]
    )

    result = await enforce_length(long_answer, revise)

    assert result == "Short enough this time."
    assert revise.call_count == 2


async def test_enforce_length_falls_back_to_sentence_trim_after_every_attempt():
    long_answer = "A sentence that says something. " * 50
    revise = AsyncMock(return_value="Still much too long. " * 60)

    result = await enforce_length(long_answer, revise)

    assert len(result) <= MAX_ANSWER_LEN
    assert result.endswith(".")
    assert revise.call_count == 3


async def test_enforce_length_survives_a_failing_reviser():
    long_answer = "A sentence that says something. " * 50
    revise = AsyncMock(side_effect=RuntimeError("provider down"))

    result = await enforce_length(long_answer, revise)

    assert len(result) <= MAX_ANSWER_LEN
    assert result.endswith(".")


async def test_enforce_length_measures_after_stripping_cite_tags():
    # 900 chars of prose plus citation markup that pushes it past the limit —
    # the markup is not content, so this must not trigger a revision.
    body = "This is a sentence about models. " * 27
    raw = f'<cite index="1-1">{body}</cite>' + '<cite index="2-2">' * 10 + "</cite>" * 10
    revise = AsyncMock()

    result = await enforce_length(raw, revise)

    revise.assert_not_called()
    assert "<cite" not in result


def test_ends_on_complete_sentence_accepts_trailing_markdown():
    assert ends_on_complete_sentence("The model stops early. **That is the bug.**")
    assert ends_on_complete_sentence('She asked, "why now?"')
    assert not ends_on_complete_sentence(
        "Defenders counter that **determined bad actors find workarounds anyway**"
    )


def test_drop_incomplete_tail_cuts_back_to_the_last_finished_sentence():
    truncated = (
        "Open weights lower the barrier for bad actors, since guardrails are just "
        "fine-tuning that can be undone. Defenders counter that **determined bad "
        "actors find workarounds anyway"
    )
    repaired = drop_incomplete_tail(truncated)
    assert repaired.endswith("fine-tuning that can be undone.")
    assert "Defenders counter" not in repaired
    # A dangling bold marker must not survive the cut.
    assert repaired.count("**") % 2 == 0


def test_drop_incomplete_tail_leaves_a_finished_answer_alone():
    finished = "A benchmark is a standardized test. It stops being useful once saturated."
    assert drop_incomplete_tail(finished) == finished


def test_drop_incomplete_tail_keeps_text_with_no_complete_sentence():
    # Nothing to salvage — the caller's error handling beats an empty answer.
    fragment = "The first thing to understand about attention is that"
    assert drop_incomplete_tail(fragment) == fragment


@pytest.mark.asyncio
async def test_enforce_length_repairs_a_truncated_answer_without_calling_the_model():
    revise = AsyncMock()
    truncated = "Benchmarks measure model performance. Saturation happens when scores"

    result = await enforce_length(truncated, revise)

    assert result == "Benchmarks measure model performance."
    revise.assert_not_awaited()


@pytest.mark.asyncio
async def test_enforce_length_retries_when_the_revision_itself_is_truncated():
    long_answer = "This sentence is complete. " * 60
    revise = AsyncMock(
        side_effect=[
            TruncatedOutputError("ran out of room"),
            "A short, complete rewrite of the answer.",
        ]
    )

    result = await enforce_length(long_answer, revise)

    assert result == "A short, complete rewrite of the answer."
    assert revise.await_count == 2
