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
- [x] RSS fetcher — feedparser for HN, arxiv, Latent Space, Simon Willison
- [x] Reddit client — OAuth token flow, fetch hot posts from 4 subreddits
- [x] Source aggregation service — combine RSS + Reddit into SourceItem list
- [x] Integration test — mock Ground Ctrl responses, verify run lifecycle

**Done when:** `POST /run` can fetch real sources and call Ground Ctrl (generation still raises NotImplementedError).

---

## Phase 3: Multi-Model Generation

- [ ] Claude generation — Anthropic SDK, 2 candidates per call
- [ ] GPT-4o generation — OpenAI SDK, 2 candidates per call
- [ ] Gemini generation — Google GenAI SDK, 2 candidates per call
- [ ] Parallel execution — asyncio.gather all three
- [ ] Generation prompt — shared prompt template with source context
- [ ] `POST /generate` endpoint working end-to-end

**Done when:** `/generate` returns 6 candidates from 3 models. Each candidate has questionMd + answerMd.

---

## Phase 4: Review + Scoring

- [ ] Review service — Claude scores all 6 candidates 1-10 with one-line reason
- [ ] Structured output — parse Claude's review into ReviewedCandidate list
- [ ] Top-3 selection — sort by score, return top 3
- [ ] `POST /run` fully wired — sources → generate → review → persist to Ground Ctrl

**Done when:** `/run` completes the full pipeline and Ground Ctrl receives 3 scored candidates.

---

## Phase 5: Styling + Choose

- [ ] Styler service — Claude normalizes content (bold key terms, 1-3 paragraphs, plain prose)
- [ ] `POST /style` endpoint working
- [ ] `POST /choose` endpoint — top candidate → resources → style → publish
- [ ] Wire choose into Ground Ctrl publish flow

**Done when:** `/style` and `/choose` work end-to-end.

---

## Phase 6: Resource Retrieval

- [ ] Embedding client — OpenAI text-embedding-3-small (1536 dims)
- [ ] Vector search — query resources table by cosine similarity
- [ ] Generative fallback — Claude suggests URL when no vector match
- [ ] `POST /retrieve-resources` endpoint working

**Done when:** `/retrieve-resources` returns relevant resources for a given question.

> **Note:** This depends on Ground Ctrl having a resources API — may need to coordinate or stub.

---

## Phase 7: Notifications

- [ ] OneSignal client — send push notifications
- [ ] Notification service — candidates_ready, publish_warning, published, nothing_to_publish
- [ ] Wire into pipeline run (after candidates persisted)
- [ ] Wire into auto-publish (after publish or on empty)

**Done when:** Push notifications fire at the right moments in the pipeline.

---

## Phase 8: Cron + Auto-Publish

- [ ] APScheduler jobs — 6:00am, 8:45am, 9:00am PT, weekdays only
- [ ] Auto-publish fallback chain:
  1. Already scheduled → publish
  2. Unreviewed run → choose for me
  3. Unpublished pool → pick + style + publish
  4. Rejected pool → pick + style + publish
  5. Nothing → push notification
- [ ] 8:45am warning — only if run is still `awaiting_review`
- [ ] DB read queries for auto-publish logic (soft-delete-aware)

**Done when:** The three cron jobs fire correctly and auto-publish works through all 5 fallback levels.

---

## Phase 9: Testing + Hardening

- [ ] Unit tests — services (generator, reviewer, styler, publisher)
- [ ] Integration tests — routes with mocked external APIs
- [ ] Error handling — retries for transient API failures
- [ ] Logging — structured logs for each pipeline stage
- [ ] Timeout handling — per-model generation timeouts

**Done when:** Test suite passes, error paths are covered, logs are actionable.

---

## Phase 10: Deploy

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
| Ground Ctrl resources API not built | Phase 6 can be deferred; stub the endpoint |
| OneSignal setup incomplete | Notifications gracefully no-op when credentials are empty |
| Reddit API rate limits | Degrade gracefully — RSS sources are sufficient alone |
| Model API outages | fail_run marks the run as failed; retry via `POST /run` |
| Python 3.7 on system PATH | Locked to 3.12 via uv + .python-version |
