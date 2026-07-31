"""Cleanup and length control for model-written answers.

Every provider leaves its own fingerprints on an answer: Claude emits
`<cite index="...">` wrappers when web search is on, models occasionally write
a literal `/n` or `\\n` instead of a real paragraph break, and all three
overrun the character budget from time to time.

Both generators (`generator.py`, `answer_generator.py`) run their output
through here so an answer reads the same wherever it came from, and so an
over-long answer gets genuinely rewritten rather than chopped mid-thought.
"""

import logging
import re

from app.clients.anthropic import get_client as get_anthropic
from app.clients.anthropic import send_with_continuation
from app.clients.gemini import generate_text as gemini_generate_text
from app.clients.openai import create_text as openai_create_text

logger = logging.getLogger(__name__)

MAX_ANSWER_LEN = 1000

# Web-search citation wrappers. The citation text itself is real prose, so the
# tags come off and the words stay.
_CITE_TAG_RE = re.compile(r"</?cite\b[^>]*>", re.IGNORECASE)
_BR_TAG_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
# OpenAI's web search annotates answers with bare-domain source links —
# `([tomshardware.com](https://...))`. Link text that is a naked domain is a
# citation, not prose, so it comes out; a real prose link keeps its wording.
_SOURCE_LINK_RE = re.compile(r"\[[^\]\s]+\.[a-z]{2,}\]\(https?://[^)\s]*\)\s*,?\s*")
_EMPTY_PARENS_RE = re.compile(r"\s*\(\s*(?:source[s]?\s*:?)?\s*\)")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([.,;:!?])")
# A literal "/n" used as a paragraph separator, only when it stands alone —
# the negative lookahead keeps it off paths like "/news" and "/notes".
_SLASH_N_RE = re.compile(r"(?:^|[ \t])/n(?![^\W_])[ \t]*", re.MULTILINE)
# A literal backslash-n that survived JSON decoding.
_ESCAPED_N_RE = re.compile(r"\\n")
_TRAILING_SPACE_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_EXTRA_BLANK_LINES_RE = re.compile(r"\n{3,}")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])(\s+)")


def sanitize_answer(text: str) -> str:
    """Strip provider markup artefacts and normalise paragraph breaks."""
    if not text:
        return ""
    # Tidying the punctuation a removed citation left behind is only safe when
    # a citation was actually removed — otherwise it would edit ordinary prose.
    if _CITE_TAG_RE.search(text) or _SOURCE_LINK_RE.search(text):
        text = _CITE_TAG_RE.sub("", text)
        text = _SOURCE_LINK_RE.sub("", text)
        text = _EMPTY_PARENS_RE.sub("", text)
        text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = _BR_TAG_RE.sub("\n\n", text)
    text = _SLASH_N_RE.sub("\n\n", text)
    text = _ESCAPED_N_RE.sub("\n", text)
    text = _TRAILING_SPACE_RE.sub("", text)
    text = _EXTRA_BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def _balance_emphasis(text: str) -> str:
    """Drop a dangling bold marker left behind by trimming."""
    if text.count("**") % 2 == 1:
        head, _, tail = text.rpartition("**")
        text = (head + tail).rstrip()
    return text


def trim_to_sentence(text: str, limit: int = MAX_ANSWER_LEN) -> str:
    """Last-resort shortening: drop whole trailing sentences, never half of one.

    Only reached when every revision attempt has failed. Cutting mid-sentence is
    the failure mode this exists to avoid, so the text is rebuilt sentence by
    sentence and anything that does not fit is dropped entirely.
    """
    if len(text) <= limit:
        return text

    pieces = _SENTENCE_SPLIT_RE.split(text)
    kept = ""
    for i in range(0, len(pieces), 2):
        sentence = pieces[i]
        separator = pieces[i + 1] if i + 1 < len(pieces) else ""
        if len(kept) + len(sentence) > limit:
            break
        kept += sentence + separator

    kept = kept.strip()
    if not kept:
        # A single sentence longer than the whole budget — cut at a word and
        # signal the cut rather than pretending the thought finished.
        kept = text[: limit - 1].rsplit(" ", 1)[0].rstrip(" ,;:—-") + "…"
    return _balance_emphasis(kept)


_REVISE_PROMPT = (
    "The answer below is {length} characters, which is too long. Rewrite it to "
    "at most {target} characters — roughly {words} words or fewer.\n\n"
    "Do not truncate it. Cut the least essential material, tighten the wording, "
    "and keep the key insight, the voice, and the markdown formatting. The "
    "rewrite must end on a complete sentence and read as a finished thought. An "
    "answer that stops mid-idea is a failure. Dropping a whole point is fine; "
    "leaving one half-made is not.\n\n"
    "Return ONLY the rewritten answer — no preamble, no quotes, no explanation.\n\n"
    "{answer}"
)

_REVISION_ATTEMPTS = 3
# Models aim by feel rather than counting, so asking for exactly the ceiling
# reliably lands just over it. Each attempt asks for a wider margin below the
# limit than the last.
_TARGET_STEP = 100
# Average characters per word in this kind of prose — models hit a word budget
# far more accurately than a character budget.
_CHARS_PER_WORD = 6


async def enforce_length(
    answer: str,
    revise_fn,
    *,
    limit: int = MAX_ANSWER_LEN,
    label: str = "answer",
) -> str:
    """Return a sanitized answer within `limit`, revising it as many times as needed.

    `revise_fn` takes a prompt and returns the model's raw text. Truncation is
    only used if every revision attempt fails or the provider errors.
    """
    answer = sanitize_answer(answer)
    if len(answer) <= limit:
        return answer

    shortest = answer
    for attempt in range(_REVISION_ATTEMPTS):
        target = max(limit - (attempt + 1) * _TARGET_STEP, limit // 2)
        logger.info(
            "%s over limit (%d > %d), revision attempt %d/%d targeting %d chars",
            label,
            len(shortest),
            limit,
            attempt + 1,
            _REVISION_ATTEMPTS,
            target,
        )
        try:
            raw = await revise_fn(
                _REVISE_PROMPT.format(
                    length=len(shortest),
                    target=target,
                    words=target // _CHARS_PER_WORD,
                    answer=shortest,
                )
            )
        except Exception as e:
            logger.warning("%s revision attempt %d failed: %s", label, attempt + 1, e)
            break
        revised = sanitize_answer(raw)
        if not revised:
            continue
        logger.info("%s revision attempt %d returned %d chars", label, attempt + 1, len(revised))
        if len(revised) <= limit:
            logger.info("%s revised: %d -> %d chars", label, len(answer), len(revised))
            return revised
        if len(revised) < len(shortest):
            shortest = revised

    logger.warning(
        "%s still %d chars after %d revisions — trimming to whole sentences",
        label,
        len(shortest),
        _REVISION_ATTEMPTS,
    )
    return trim_to_sentence(shortest, limit)


async def revise_with_claude(prompt: str) -> str:
    raw, _ = await send_with_continuation(
        get_anthropic(),
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return raw.strip()


async def revise_with_gpt4(prompt: str) -> str:
    return await openai_create_text(
        model="gpt-4o",
        user=prompt,
        max_output_tokens=1024,
        web_search=False,
    )


async def revise_with_gemini(prompt: str) -> str:
    return await gemini_generate_text(
        model="gemini-2.5-flash",
        contents=prompt,
        max_output_tokens=1024,
        web_search=False,
    )
