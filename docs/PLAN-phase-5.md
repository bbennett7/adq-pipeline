---
plan: docs/PLAN.md
phase: "Phase 5: Styling + Choose"
status: completed
date: 2026-05-23
---

# Phase Brief: Styling + Choose

## Goal

Implement the styling service (Claude normalizes question/answer formatting) and the choose endpoint (pick top candidate from a run, optionally retrieve resources, style it, and publish via Ground Ctrl). This phase bridges the gap between reviewed candidates (Phase 4) and a published question — it's the last step before the cron/auto-publish logic can be wired up in Phase 8.

## Context from the Plan

> - Styler service — Claude normalizes content (bold key terms, 1-3 paragraphs, plain prose)
> - `POST /style` endpoint working
> - `POST /choose` endpoint — top candidate → resources → style → publish
> - Wire choose into Ground Ctrl publish flow
>
> Done when: `/style` and `/choose` work end-to-end.

---

## Branch Strategy

Single branch — the phase is cohesive (one service, two endpoints, one Ground Ctrl method) and doesn't warrant splitting.

| Branch | Scope | Merges into |
|--------|-------|-------------|
| `feat/style-choose-phase-5` | Styler service, style/choose endpoints, Ground Ctrl publish method, tests | `main` |

**Commit strategy:** Use `commit-review` at each logical stopping point during implementation.

---

## Step-by-Step Approach

### Step 1 — Create the styler prompt

Create `app/prompts/styler.txt` following the pattern of `app/prompts/reviewer.txt` and `app/prompts/generator.txt`. The prompt instructs Claude to normalize a question/answer pair:
- Question: one sentence, bold-italic 1-2 keywords
- Answer: 1-3 short paragraphs, bold key terms on first use, no bullet lists, plain prose
- Return JSON: `{"questionMd": "...", "answerMd": "..."}`
- Return ONLY the JSON, no other text

**Verify:** File exists, content is a clear prompt matching the formatting rules from generator.txt examples.

### Step 2 — Implement `style_content` in `app/services/styler.py`

Replace the existing stub (`raise NotImplementedError`) with real logic:
- Load the system prompt from `app/prompts/styler.txt` (same pattern as `reviewer.py:11`)
- Use `app/clients/anthropic.get_client()` to call Claude (same pattern as `reviewer.py:60-67`)
- Model: `claude-sonnet-4-6` (matches reviewer)
- Parse JSON response to extract `questionMd` and `answerMd`
- Return `(styled_question_md, styled_answer_md)` tuple
- Handle JSON parse errors with a clear log + re-raise (same pattern as `reviewer.py:69-73`)

**Verify:** `uv run ruff check app/services/styler.py` passes. Manually confirm the function signature matches what `app/routes/style.py:18` expects: `style_content(question_md: str, answer_md: str) -> tuple[str, str]`.

### Step 3 — Add Ground Ctrl `choose_candidate` and `publish_question` methods

Add two methods to `app/clients/ground_ctrl.py`:

1. `choose_candidate(run_id: str, candidate_id: str)` — `POST /api/pipeline/runs/{runId}/choose` with `{"candidateId": candidate_id}`. This tells Ground Ctrl which candidate was selected. Returns the response JSON (which should include the created question).

2. `publish_question(question_id: str, styled_question_md: str, styled_answer_md: str)` — `POST /api/pipeline/questions/{questionId}/publish` with the styled content. Returns the response JSON.

Follow the existing pattern: use `self._client()` context manager, `resp.raise_for_status()`.

**Verify:** `uv run ruff check app/clients/ground_ctrl.py` passes. Methods have correct signatures and follow existing patterns.

### Step 4 — Implement the `/choose` endpoint

Update `app/routes/choose.py` to accept a request body and orchestrate:

1. Accept `ChooseRequest` with `run_id: str` and optional `candidate_id: str | None`
2. If no `candidate_id`, fetch the run via `gc.get_run(run_id)`, select the top-scoring non-deleted candidate
3. Call `gc.choose_candidate(run_id, candidate_id)` to tell Ground Ctrl
4. Run `style_content(question_md, answer_md)` on the chosen candidate
5. Call `gc.publish_question(question_id, styled_q, styled_a)` to publish
6. Return the result

Note: Resource retrieval (`retrieve_resources`) is Phase 6 and still raises NotImplementedError. Do NOT call it from `/choose` yet — that integration is deferred to Phase 6.

**Verify:** `uv run ruff check app/routes/choose.py` passes. Endpoint can be called with a run_id and will orchestrate the choose → style → publish flow.

### Step 5 — Write tests

Create `tests/test_styler.py`:
- Test `style_content` with a mocked Anthropic client returning valid JSON
- Test parse-error handling (malformed JSON from Claude)

Update `tests/test_ground_ctrl.py` (if it exists and has patterns for the existing methods):
- Test `choose_candidate` with mocked httpx response
- Test `publish_question` with mocked httpx response

Create `tests/test_choose.py`:
- Test the `/choose` endpoint end-to-end with mocked Ground Ctrl + Anthropic
- Test the auto-pick behavior (no candidate_id, picks top scorer)

**Verify:** `uv run pytest` passes. All new tests pass.

### Step 6 — Lint + format

Run `uv run ruff check .` and `uv run ruff format .` across the whole project.

**Verify:** Zero lint errors, zero format changes.

---

## Unknowns

| Unknown | Why it matters | How to resolve |
|---------|---------------|----------------|
| Ground Ctrl `/choose` and `/publish` endpoint shapes | We're assuming `POST /api/pipeline/runs/{runId}/choose` and `POST /api/pipeline/questions/{questionId}/publish` exist with the payloads described | Check Ground Ctrl codebase or test against the live API. If not built yet, implement the pipeline side to the assumed contract and note it needs coordination. |
| Whether `choose_candidate` returns a `questionId` | The pipeline needs a `questionId` to call `publish_question` | Assume the choose response includes `{"question": {"id": "..."}}`. If it doesn't, the publish step will need the question ID from another source. |
| Styling prompt edge cases | The styler needs to handle content that's already well-formatted without mangling it | Write the prompt to be idempotent — "normalize to this format" rather than "reformat this" |

---

## Outputs

| Output | Type | Description |
|--------|------|-------------|
| `app/prompts/styler.txt` | New file | System prompt for the Claude styling pass |
| `app/services/styler.py` | Modified | Real implementation replacing the NotImplementedError stub |
| `app/clients/ground_ctrl.py` | Modified | New `choose_candidate` and `publish_question` methods |
| `app/routes/choose.py` | Modified | Full implementation of the choose → style → publish flow |
| `tests/test_styler.py` | New file | Unit tests for the styler service |
| `tests/test_choose.py` | New file | Integration tests for the choose endpoint |

---

## Done Criteria

- [ ] `POST /style` returns styled `questionMd` and `answerMd` from Claude (not NotImplementedError)
- [ ] `POST /choose` with a `run_id` selects top candidate, styles it, and publishes via Ground Ctrl
- [ ] `POST /choose` with a `run_id` and explicit `candidate_id` uses that candidate instead of auto-picking
- [ ] Styler prompt produces output matching the format rules (bold-italic keywords in question, bold key terms in answer, 1-3 paragraphs, no bullets)
- [ ] Ground Ctrl client has `choose_candidate` and `publish_question` methods
- [ ] All tests pass: `uv run pytest`
- [ ] Linter passes: `uv run ruff check .`

---

## What This Phase Does NOT Include

- Resource retrieval (`POST /retrieve-resources`) — that's Phase 6. The choose flow does NOT call `retrieve_resources` yet.
- Auto-publish / cron scheduling — Phase 8
- Push notifications wired into choose/publish — Phase 7
- The publisher service (`app/services/publisher.py`) auto-publish fallback chain — Phase 8

---

## Handoff to Next Phase

- Phase 6 (Resources) can add a resource retrieval step into the choose flow after `style_content` and before `publish_question`
- Phase 7 (Notifications) can add `notify_published(question)` at the end of the choose flow
- Phase 8 (Cron + Auto-Publish) depends on `choose` working end-to-end — the auto-publish fallback chain calls the same choose → style → publish orchestration
