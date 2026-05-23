import json
import logging
from pathlib import Path

from app.clients.anthropic import get_client

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
SYSTEM_PROMPT = (_PROMPTS_DIR / "styler.txt").read_text().strip()


async def style_content(question_md: str, answer_md: str) -> tuple[str, str]:
    """Claude styling pass — normalize to plain prose, bold key terms, 1-3 paragraphs.

    Returns (styled_question_md, styled_answer_md).
    """
    client = get_client()
    user_input = f"Question: {question_md}\n\nAnswer: {answer_md}"

    response = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_input}],
    )
    raw = response.content[0].text

    try:
        data = json.loads(raw)
        styled_q = data["questionMd"]
        styled_a = data["answerMd"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error("Styler parse failed: %s — raw: %.500s", e, raw)
        raise ValueError(f"Claude styler returned unparseable response: {e}") from e

    return styled_q, styled_a
