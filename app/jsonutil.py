import json
import re

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def extract_json_object(raw: str) -> dict:
    """Parse a JSON object from model output that may surround it with prose.

    Models with web search enabled often narrate their reasoning before the
    JSON, so try, in order: the whole text, any fenced code block, and the
    outermost {...} span.

    Raises ValueError if no JSON object can be extracted.
    """
    candidates = [raw.strip()]
    candidates.extend(m.strip() for m in _FENCED_JSON_RE.findall(raw))
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        candidates.append(raw[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    raise ValueError(f"No JSON object found in response: {raw[:200]!r}")
