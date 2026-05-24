# adq-pipeline — Implementation Plan

## Status Key

- [ ] Not started
- [x] Complete

---

## Phase 1: Foundation (scaffolding, config, health)

- [x] Project init — uv, Python 3.12, pyproject.toml with all deps
- [x] Directory structure — app/{routes,services,clients,models,cron}, tests/
- [x] Config — pydantic-settings from env vars, deferred instantiation
- [x] Date utilities — PT/UTC conversions, `today_pt()`, `to_publish_timestamp()`
- [x] Auth middleware — shared secret bearer token verification
- [x] DB pool — asyncpg read-only connection pool with lifespan cleanup
- [x] FastAPI app — lifespan, route registration, health endpoint
- [x] Pydantic models — Run, Candidate, GeneratedCandidate, ReviewedCandidate, SourceItem
- [x] Dockerfile + fly.toml
- [x] Lint clean (ruff)

---

## Phase 2: Ground Ctrl Client + Source Fetching

- [x] Ground Ctrl HTTP client — create_run, submit_candidates, fail_run, get_run (stubs wired)
- [x] RSS fetcher — async httpx fetch with 15s timeout, feedparser for HN, arxiv, Latent Space
- [x] Reddit client — OAuth token flow, concurrent subreddit fetching with 15s timeout
- [x] Source aggregation service — combine RSS + Reddit with fault isolation (return_exceptions)
- [x] Integration test — mock Ground Ctrl responses, verify run lifecycle
- [x] Hardening — timing-safe auth, summary truncation via model validator, bozo feed logging, graceful degradation at every level

**Done when:** `POST /run` can fetch real sources and call Ground Ctrl (generation still raises NotImplementedError).

---

## Phase 3: Multi-Model Generation

- [x] Claude generation — Anthropic SDK, 2 candidates per call
- [x] GPT-4o generation — OpenAI SDK, 2 candidates per call
- [x] Gemini generation — Google GenAI SDK, 2 candidates per call
- [x] Parallel execution — asyncio.gather all three
- [x] Generation prompt — shared prompt template with source context
- [x] `POST /generate` endpoint working end-to-end

**Done when:** `/generate` returns 6 candidates from 3 models. Each candidate has questionMd + answerMd.

---

## Phase 4: Review + Scoring

- [x] Review service — Claude scores all 6 candidates 1-10 with one-line reason
- [x] Structured output — parse Claude's review into ReviewedCandidate list
- [x] Top-3 selection — sort by score, return top 3
- [x] `POST /run` fully wired — sources → generate → review → persist to Ground Ctrl

**Done when:** `/run` completes the full pipeline and Ground Ctrl receives 3 scored candidates.

---

## Phase 5: Styling + Choose

- [x] Styler service — Claude normalizes content (bold key terms, 1-3 paragraphs, plain prose)
- [x] `POST /choose` endpoint — top candidate → style → publish via Ground Ctrl

**Done when:** `/choose` works end-to-end.

---

## Phase 6: Resource Retrieval

- [ ] Resource suggestion prompt — Claude suggests relevant URLs given a question + answer
- [ ] Resource service — parse Claude response into structured resources (url, label, source, author)
- [ ] `POST /retrieve-resources` endpoint working

**Done when:** `/retrieve-resources` returns relevant structured resources for a given question.

---

## ~~Phase 7: Notifications~~ (removed — not pipeline's responsibility)

## ~~Phase 8: Cron + Auto-Publish~~ (removed — not pipeline's responsibility)

---

## Phase 7: Testing + Hardening

- [ ] Unit tests — services (generator, reviewer, styler, publisher)
- [ ] Integration tests — routes with mocked external APIs
- [ ] Error handling — retries for transient API failures
- [ ] Logging — structured logs for each pipeline stage
- [ ] Timeout handling — per-model generation timeouts

**Done when:** Test suite passes, error paths are covered, logs are actionable.

---

## Phase 8: Deploy

- [ ] Set Fly.io secrets (all env vars)
- [ ] First deploy — `fly deploy`
- [ ] Verify health check — `GET /health`
- [ ] Test Ground Ctrl → Pipeline auth (both directions)
- [ ] Trigger a test run from Ground Ctrl admin
- [ ] Monitor first automated 6am run

**Done when:** Pipeline runs autonomously on weekday mornings, auto-publishes by 9am.

---

## Dependencies & Risks

| Risk | Mitigation |
|------|------------|
| Reddit API rate limits | Degrade gracefully — RSS sources are sufficient alone |
| Model API outages | fail_run marks the run as failed; retry via `POST /run` |
| Python 3.7 on system PATH | Locked to 3.12 via uv + .python-version |
