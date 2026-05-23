---
plan: docs/PLAN.md
phase: "Phase 6: Resource Retrieval"
status: pending
date: 2026-05-23
---

# Phase Brief: Resource Retrieval

## Goal

Implement the resource retrieval service that finds relevant resources (links) to attach to a published question. Given a question and answer, the pipeline uses Claude to suggest structured resources — URLs, labels, sources, and optional authors — that a curious reader would want to explore. This is a purely generative task: no DB access, no embeddings, no vector search. The pipeline takes in content and returns structured resource suggestions.

## Context from the Plan

> - Embedding client — OpenAI text-embedding-3-small (1536 dims)
> - Vector search — query resources table by cosine similarity
> - Generative fallback — Claude suggests URL when no vector match
> - `POST /retrieve-resources` endpoint working
>
> Done when: `/retrieve-resources` returns relevant resources for a given question.

**Plan correction:** The original plan assumed the pipeline would do embeddings + vector search against the DB. The pipeline never has DB access for resource retrieval. The approach is purely generative — Claude suggests relevant resources given the question + answer content. The resources table and embeddings are Ground Ctrl's domain.

---

## Branch Strategy

Single branch — phase scope is small and cohesive (one service, one prompt, one model, tests).

| Branch | Scope | Merges into |
|--------|-------|-------------|
| `feat/resource-retrieval-phase-6` | Resource service, prompt, model, tests | `main` |

**Commit strategy:** Use `commit-review` at each logical stopping point during implementation.

---

## Step-by-Step Approach

### Step 1 — Create Pydantic model for ResourceSuggestion

Add `app/models/resources.py` with a model representing a resource the pipeline suggests:

```python
class ResourceSuggestion(BaseModel):
    url: str
    label: str
    source: str
    author: str | None = None
```

This matches the shape Ground Ctrl expects (see `ResourceLinkSchema` in the adq codebase: `{ label, url, source, author? }`).

**Verify:** `uv run ruff check app/models/resources.py` passes.

### Step 2 — Create the resource retrieval prompt

Create `app/prompts/resources.txt` following the pattern of existing prompts (`styler.txt`, `reviewer.txt`). The prompt instructs Claude to:

- Given a question and answer, suggest 1-3 relevant web resources (articles, Wikipedia pages, academic papers, official documentation, etc.) that a curious reader would want to explore after reading the Q&A
- Each resource needs: `url`, `label` (short description, e.g. "Wikipedia: Eyebrow"), `source` (domain/publication, e.g. "wikipedia.org"), and optional `author`
- URLs must be real, well-known, and highly likely to exist — prefer Wikipedia, major publications, official documentation, established reference sites
- Do NOT invent or hallucinate URLs — if unsure a URL exists, don't include it
- Return JSON: `{"resources": [{"url": "...", "label": "...", "source": "...", "author": "..."}]}`
- Return ONLY the JSON, no other text

**Verify:** File exists at `app/prompts/resources.txt`.

### Step 3 — Implement `retrieve_resources` in `app/services/resources.py`

Replace the `NotImplementedError` stub. The service:

1. Loads the system prompt from `app/prompts/resources.txt` (same pattern as `styler.py:10-11`)
2. Combines `question_md` and `answer_md` into the user message
3. Calls `app/clients/anthropic.get_client()` with `claude-sonnet-4-6` (same pattern as `reviewer.py:60-67`)
4. Parses the JSON response to extract the resources list
5. Validates each resource against `ResourceSuggestion`
6. Returns the resources as a `list[dict]`
7. On parse errors: logs the error and returns an empty list (resource suggestions are non-critical — don't crash the pipeline)

**Verify:** `uv run ruff check app/services/resources.py` passes. Function signature still matches the route: `retrieve_resources(question_md: str, answer_md: str) -> list[dict]`.

### Step 4 — Verify the route

The route at `app/routes/resources.py` is already wired and should work as-is. Confirm:
- Accepts `question_md` and `answer_md` in the request body
- Returns `{"resources": [...]}`
- Auth is required via `verify_token`

No changes expected — just verify.

**Verify:** `uv run ruff check app/routes/resources.py` passes.

### Step 5 — Write tests

Create `tests/test_resources.py`:

1. **Test successful resource retrieval** — mock Anthropic client returning valid JSON with resources, verify the service returns parsed resources
2. **Test parse error graceful handling** — mock Anthropic client returning malformed JSON, verify service returns empty list (not an exception)
3. **Test endpoint integration** — use the `client` fixture to call `POST /retrieve-resources` with mocked Anthropic client, verify 200 with correct shape
4. **Test auth required** — call endpoint without auth header, verify 401/403

Follow the test patterns from `tests/test_choose.py` (mock Anthropic via `patch`, use `SimpleNamespace` for response objects).

**Verify:** `uv run pytest tests/test_resources.py` passes.

### Step 6 — Lint + format

Run `uv run ruff check .` and `uv run ruff format .` across the whole project.

**Verify:** Zero lint errors, zero format changes.

---

## Unknowns

| Unknown | Why it matters | How to resolve |
|---------|---------------|----------------|
| Claude's reliability for suggesting real URLs | LLMs can hallucinate URLs that don't exist | Prompt strongly for well-known, high-probability URLs (Wikipedia, major publications). Accept that some may be stale — Ground Ctrl can validate/filter downstream if needed. |
| How many resources to suggest | Too many dilutes quality, too few may miss useful links | Start with 1-3 in the prompt. Can be tuned based on real output quality. |

---

## Outputs

| Output | Type | Description |
|--------|------|-------------|
| `app/models/resources.py` | New file | `ResourceSuggestion` Pydantic model |
| `app/prompts/resources.txt` | New file | System prompt for Claude resource suggestions |
| `app/services/resources.py` | Modified | Full implementation replacing NotImplementedError — Claude generates resource suggestions |
| `tests/test_resources.py` | New file | Tests for service + endpoint |

---

## Done Criteria

- [ ] `POST /retrieve-resources` returns a 200 with `{"resources": [...]}` containing structured resource objects (not NotImplementedError)
- [ ] Each resource has `url`, `label`, `source`, and optional `author`
- [ ] Parse errors from Claude are handled gracefully (logged, return empty list)
- [ ] Auth is required on the endpoint (401/403 without token)
- [ ] All tests pass: `uv run pytest`
- [ ] Linter passes: `uv run ruff check .`

**Do not mark the phase complete until every item above is checked.**

---

## What This Phase Does NOT Include

- Embeddings or vector search — not the pipeline's responsibility
- DB access — the pipeline never queries the resources table
- Writing/linking resources to questions — Ground Ctrl's domain
- Integrating resource retrieval into the `/choose` endpoint — small follow-up task after this phase
- URL validation (checking that suggested URLs actually resolve) — can be added later if needed

---

## Handoff to Next Phase

- The `/choose` endpoint can be updated to call `retrieve_resources` and include results in the publish payload to Ground Ctrl
- Phase 7 (Notifications) and Phase 8 (Cron + Auto-Publish) are independent of this phase
