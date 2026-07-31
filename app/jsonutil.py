import json
import re

_FENCED_JSON_RE = re.compile(r"```(?:json)?\s*\n(.*?)```", re.DOTALL)


def _escape_control_chars_in_strings(raw: str) -> str:
    """Escape raw newlines and tabs that appear inside JSON string literals.

    Models write multi-paragraph answers with real line breaks inside the
    quoted value, which is invalid JSON and fails the whole parse. Escaping
    them in place recovers the object without touching the structure.
    """
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in raw:
        if not in_string:
            if ch == '"':
                in_string = True
            out.append(ch)
        elif escaped:
            out.append(ch)
            escaped = False
        elif ch == "\\":
            out.append(ch)
            escaped = True
        elif ch == '"':
            in_string = False
            out.append(ch)
        elif ch in "\n\r\t":
            out.append({"\n": "\\n", "\r": "\\r", "\t": "\\t"}[ch])
        else:
            out.append(ch)
    return "".join(out)


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
        for attempt in (candidate, _escape_control_chars_in_strings(candidate)):
            try:
                data = json.loads(attempt)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
    raise ValueError(f"No JSON object found in response: {raw[:200]!r}")
