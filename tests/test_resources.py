import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

FAKE_RESOURCES_JSON = json.dumps(
    {
        "resources": [
            {
                "url": "https://en.wikipedia.org/wiki/Eyebrow",
                "label": "Wikipedia: Eyebrow",
                "source": "wikipedia.org",
            },
            {
                "url": "https://www.scientificamerican.com/article/why-do-we-have-eyebrows/",
                "label": "Why Do We Have Eyebrows?",
                "source": "scientificamerican.com",
                "author": "Jane Smith",
            },
        ]
    }
)

_Q = "Why do we have eyebrows if they do not actually keep the rain out of our eyes?"
_A = (
    "**Eyebrows** serve a surprisingly important role in human communication and expression. "
    "They help channel sweat and rain away from your eyes, but their real superpower is social."
)


def _mock_anthropic(response_text: str = FAKE_RESOURCES_JSON) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(text=response_text, type="text")],
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=100, output_tokens=200),
    )
    return mock_client


async def test_retrieve_resources_returns_parsed_resources():
    anthropic_client = _mock_anthropic()

    with patch("app.services.resources.get_client", return_value=anthropic_client):
        from app.services.resources import retrieve_resources

        result = await retrieve_resources(_Q, _A)

    assert len(result) == 2
    assert result[0]["url"] == "https://en.wikipedia.org/wiki/Eyebrow"
    assert result[0]["label"] == "Wikipedia: Eyebrow"
    assert result[0]["source"] == "wikipedia.org"
    assert "author" not in result[0]
    assert result[1]["author"] == "Jane Smith"


async def test_retrieve_resources_strips_code_fences():
    fenced = f"```json\n{FAKE_RESOURCES_JSON}\n```"
    anthropic_client = _mock_anthropic(fenced)

    with patch("app.services.resources.get_client", return_value=anthropic_client):
        from app.services.resources import retrieve_resources

        result = await retrieve_resources(_Q, _A)

    assert len(result) == 2
    assert result[0]["url"] == "https://en.wikipedia.org/wiki/Eyebrow"


async def test_retrieve_resources_returns_empty_on_malformed_json():
    anthropic_client = _mock_anthropic("not valid json at all")

    with patch("app.services.resources.get_client", return_value=anthropic_client):
        from app.services.resources import retrieve_resources

        result = await retrieve_resources(_Q, _A)

    assert result == []


async def test_retrieve_resources_returns_empty_on_missing_key():
    anthropic_client = _mock_anthropic(json.dumps({"wrong_key": []}))

    with patch("app.services.resources.get_client", return_value=anthropic_client):
        from app.services.resources import retrieve_resources

        result = await retrieve_resources(_Q, _A)

    assert result == []


async def test_retrieve_resources_endpoint(client, auth_headers):
    anthropic_client = _mock_anthropic()

    with patch("app.services.resources.get_client", return_value=anthropic_client):
        resp = client.post(
            "/retrieve-resources",
            json={"question_md": _Q, "answer_md": _A},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "resources" in data
    assert len(data["resources"]) == 2
    assert data["resources"][0]["url"] == "https://en.wikipedia.org/wiki/Eyebrow"


async def test_retrieve_resources_requires_auth(client):
    resp = client.post(
        "/retrieve-resources",
        json={"question_md": _Q, "answer_md": _A},
    )
    assert resp.status_code in (401, 403)


# --- choose-resources tests ---

_WIKI = "https://en.wikipedia.org/wiki/Eyebrow"

FIVE_RESOURCES = [
    {"url": _WIKI, "label": "Wikipedia: Eyebrow", "source": "wikipedia.org"},
    {"url": "https://example.com/1", "label": "Article 1", "source": "example.com"},
    {
        "url": "https://example.com/2",
        "label": "Article 2",
        "source": "example.com",
        "author": "Alice",
    },
    {"url": "https://example.com/3", "label": "Article 3", "source": "example.com"},
    {
        "url": "https://example.com/4",
        "label": "Article 4",
        "source": "example.com",
        "author": "Bob",
    },
]

VALIDATED_JSON = json.dumps(
    {
        "resources": [
            {
                "url": _WIKI,
                "label": "Wikipedia: Eyebrow",
                "source": "wikipedia.org",
            },
            {
                "url": "https://example.com/2",
                "label": "Article 2",
                "source": "example.com",
                "author": "Alice",
            },
            {
                "url": "https://example.com/4",
                "label": "Article 4",
                "source": "example.com",
                "author": "Bob",
            },
        ]
    }
)


async def test_validate_resources_selects_best():
    anthropic_client = _mock_anthropic(VALIDATED_JSON)

    with patch("app.services.resources.get_client", return_value=anthropic_client):
        from app.services.resources import validate_resources

        result = await validate_resources(_Q, _A, FIVE_RESOURCES)

    assert len(result) == 3
    assert result[0]["url"] == "https://en.wikipedia.org/wiki/Eyebrow"
    assert result[1]["author"] == "Alice"


async def test_validate_resources_skips_claude_when_two_or_fewer():
    from app.services.resources import validate_resources

    two = FIVE_RESOURCES[:2]
    result = await validate_resources(_Q, _A, two)

    assert result == two


async def test_validate_resources_returns_original_on_parse_error():
    anthropic_client = _mock_anthropic("not json")

    with patch("app.services.resources.get_client", return_value=anthropic_client):
        from app.services.resources import validate_resources

        result = await validate_resources(_Q, _A, FIVE_RESOURCES)

    assert result == FIVE_RESOURCES


async def test_choose_resources_endpoint(client, auth_headers):
    anthropic_client = _mock_anthropic(VALIDATED_JSON)

    with patch("app.services.resources.get_client", return_value=anthropic_client):
        resp = client.post(
            "/choose-resources",
            json={"question_md": _Q, "answer_md": _A, "resources": FIVE_RESOURCES},
            headers=auth_headers,
        )

    assert resp.status_code == 200
    data = resp.json()
    assert len(data["resources"]) == 3


async def test_choose_resources_requires_auth(client):
    resp = client.post(
        "/choose-resources",
        json={"question_md": _Q, "answer_md": _A, "resources": FIVE_RESOURCES},
    )
    assert resp.status_code in (401, 403)
