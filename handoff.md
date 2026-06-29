# HSG Factory — Handoff Doc (for Claude Code)

**Context:** This project implements the "History Shorts Generator" — a
multi-agent content pipeline that generates, scores, scripts, renders, and
publishes short-form historical videos with a human approval checkpoint.
Two source docs define the design (both should be in the repo or provided
alongside this handoff):

- `history-shorts-generator-spec.md` — full production architecture spec
  (data schema, pipeline stages, Claude prompt templates per stage, cost
  controls, quality scoring framework, topic engine, style bible system,
  script structure).
- `agent-handoff-workflow.md` — companion doc describing how the three
  agents communicate: Postgres as source of truth, Obsidian (via the Local
  REST API plugin) as a human-facing mirror that never originates state,
  polling instead of direct agent-to-agent calls, and the human checkpoint
  sitting between Generation and Publishing.

## Overall plan (5 phases)

1. **Postgres schema + Obsidian handoff layer** — ✅ done (this handoff)
2. **Agent A — Generation** — not started
3. **Agent B — Publishing** — not started
4. **Agent B — Reporting** — not started
5. **Scheduler / cron entrypoints per agent** — not started

## Current goal

Build **Agent A (Generation)**: the pipeline that pulls a topic, runs it
through Research → Validation → Script → Storyboard → Style Bible
resolution → Visual Prompts → Higgsfield scene generation → Voiceover →
Subtitles → Music → Assembly → Thumbnail, and lands a fully assembled draft
job in Postgres + a mirrored note in Obsidian's "Pending Review/" folder.

Each stage should be implemented as a pure function `(job) -> partial_update`
that gets persisted via `db.updateJob()`. The Claude prompt templates for
each reasoning stage are already specified in Section 4 of
`history-shorts-generator-spec.md` — they need wiring into real Anthropic
API calls with strict JSON-mode parsing and schema validation against the
TypeScript interfaces in Section 2 of that spec, before each
`db.updateJob()` write.

## Current state

A local Node.js scaffold exists implementing the foundation layer only
(Phase 1). No agent/pipeline logic has been written yet. Nothing has been
run against a live database or a live Obsidian vault — this is unexecuted,
reviewed-on-paper code. Treat it as a draft to validate, not a working system.

### Files touched (all new, created from scratch this session)

```
hsg-factory/
├── README.md           — project overview + setup steps + next-steps list
├── package.json         — deps: pg, dotenv. No test runner configured yet.
├── .env.example          — DATABASE_URL, OBSIDIAN_BASE_URL/API_KEY,
│                           ANTHROPIC_API_KEY, HIGGSFIELD_API_KEY,
│                           YOUTUBE_* creds (none filled in — placeholders only)
├── db/
│   └── schema.sql        — Postgres schema, 1:1 with HSGJob interface
└── src/
    ├── db.js              — data access layer (CRUD + idempotent publish)
    ├── obsidian.js         — Local REST API client (write/poll/move notes)
    └── reconcile.js         — sync loop: Postgres <-> Obsidian polling
```

### What changed / what each file does

- **`db/schema.sql`** — Tables: `style_bibles` (created before `hsg_jobs`
  because of the FK), `hsg_jobs` (the canonical job state, JSONB column per
  HSGJob key, plus `review_status` tracked separately from pipeline
  `status` since a job can be mid-render and pending-review simultaneously),
  `topic_history` (backlog + dedup via `pg_trgm` trigram similarity on
  title — noted as a placeholder for embedding-based cosine similarity
  later), `scoring_weights` (per-category, feedback-adjusted),
  `publish_results` (UNIQUE constraint on `(platform, post_id)` is what
  makes publishing idempotent), `analytics_snapshots` and `reports` (for
  the Reporting agent, not yet built). An `updated_at` trigger keeps
  `hsg_jobs` fresh on every write.

- **`src/db.js`** — `createJob`, `updateJob` (generic partial-merge writer
  any stage function can call), `appendError`/`incrementRetry` (for the
  gated-retry logic described in spec Section 3), `getJob`,
  `getJobsAwaitingObsidianSync` (jobs with `assembly IS NOT NULL` and no
  sync timestamp yet — this is what `reconcile.js` pushes),
  `markObsidianSynced`, `applyReviewDecision` (writes back a human
  approve/reject from Obsidian), `recordPublishResult` (checks
  `publish_results` for an existing row before inserting — the idempotency
  guard called out in the handoff doc's Section 6).

- **`src/obsidian.js`** — Wraps the Obsidian Local REST API plugin
  (`PUT /vault/...`, `POST /search/simple/`, `DELETE /vault/...`).
  `renderJobNote` builds the frontmatter+body markdown matching the
  handoff doc's Section 3.1 schema exactly. `writeJobNote`,
  `pollApprovedJobs`/`pollRejectedJobs`, `moveToPublished` (reads the note,
  rewrites frontmatter, PUTs to `Published/`, deletes the old one — delete
  failure is logged as non-fatal since Postgres has already moved on),
  `writeReportNote` (Section 3.2 payload, for the not-yet-built Reporting
  agent).

- **`src/reconcile.js`** — The actual inter-agent communication mechanism.
  Deliberately its own script (meant to run on its own 5-min cron tick),
  not bolted onto any single agent, so a bug in Agent A's generation logic
  can't take down the Obsidian sync. Does three things per tick:
  push unsynced drafts to Obsidian, pull approved-note statuses back into
  Postgres, pull rejected-note statuses back into Postgres (with a TODO
  left to auto-select the next-best backlog topic on rejection — not
  implemented).

## What failed / known gaps

- **Nothing has actually been executed.** No `npm install`, no
  `createdb`/schema apply, no live Obsidian REST API call, no Anthropic API
  call. There may be bugs that only surface on first run (e.g. unverified
  assumptions about the exact JSON shape the Local REST API plugin's
  `/search/simple/` endpoint returns — the code assumes
  `result.frontmatter.<field>` is present per match, which should be
  double-checked against the plugin's actual response format before
  relying on it).
- **`pollApprovedJobs`** filters out notes with a `scheduled_time` already
  set, but does this client-side after fetching all `status:approved`
  matches — fine at small scale, but will need a real query if the backlog
  grows.
- **No tests** of any kind exist yet.
- **No retry/backoff** wrapping the Obsidian or Anthropic API calls — a
  single failed fetch just logs and moves on until the next cron tick.
- **Topic Engine, Scoring Engine, Research/Validation/Script/Storyboard
  Engines, Style Bible bootstrap, Higgsfield scene generation, Voiceover/
  Subtitle/Music/Assembly/Thumbnail stages — none of this exists yet.**
  This is the bulk of Agent A and is the next deliverable.
- **No `logs/` directory** has been created despite the README's cron
  example redirecting output there.
- **Auto-promotion of the next backlog topic on rejection** (mentioned in
  the original handoff workflow doc's trigger table) is stubbed as a TODO
  comment in `reconcile.js`, not implemented.

## What you should do next

1. **Validate the foundation before building on it:**
   - `npm install`, create a local Postgres DB, run `db/schema.sql`
     end-to-end and confirm it applies cleanly (watch for the
     `style_bibles` → `hsg_jobs` FK ordering, and confirm `pg_trgm`/
     `pgcrypto` extensions are available in the target Postgres version).
   - Install the Obsidian "Local REST API" community plugin, generate an
     API key, create the `Pending Review/`, `Published/`, `Reports/`
     vault folders, and manually verify `obsidian.js`'s requests against
     the plugin's actual API responses (especially `/search/simple/` —
     confirm the per-result shape matches what `pollApprovedJobs`/
     `pollRejectedJobs` expect, and adjust if not).
   - Run `reconcile.js` against a couple of hand-inserted test rows in
     `hsg_jobs` to confirm the push/pull cycle actually works before
     building Agent A on top of it.

2. **Build Agent A (Generation)**, stage by stage, in pipeline order
   (spec Section 3): Topic Generation → Topic Scoring → Fact Research →
   Fact Validation → Script Generation → Storyboard Generation →
   Character/Style Bible resolution → Visual Prompt Generation →
   Higgsfield Scene Generation → Voiceover → Subtitles → Music Selection →
   Video Assembly → Thumbnail Creation. Suggested approach:
   - One file per stage under `src/stages/`, each exporting a function
     `(job) -> Promise<partial_update>`.
   - A thin `src/agent-a.js` entrypoint that loads the next eligible job
     (or creates one from the topic backlog), runs stages in sequence,
     calls `db.updateJob()` after each, uses `db.incrementRetry()` +
     `db.appendError()` on failure, and stops/marks `status: failed` once
     `retries[stage]` exceeds a configurable max.
   - Claude calls should use strict JSON-mode prompts (templates already
     written in spec Section 4) and validate parsed output against the
     relevant TypeScript interface in spec Section 2 before persisting —
     do not persist unvalidated model output.
   - Style Bible bootstrap/reuse logic should follow spec Section 14
     exactly (bootstrap once per category+era+visual_style, reuse via
     `style_bible_ref`, version-bump rather than mutate on refresh).
   - Cost controls from spec Section 11 (e.g. `get_cost:true` preflighting
     before bulk Higgsfield scene generation, resolution-matched
     rendering, reuse-over-regenerate for recurring characters) should be
     respected in the Higgsfield Scene Generation stage, not bolted on
     later.

3. Once Agent A reliably produces an assembled draft + synced Obsidian
   note, move to **Agent B (Publishing)** — reads jobs where
   `review_status = 'approved'` (already kept current by `reconcile.js`),
   generates platform metadata, calls the YouTube Data API, then
   `db.recordPublishResult()` (idempotency already implemented) and
   `obsidian.moveToPublished()` (already implemented).

4. Then **Agent B (Reporting)** — pulls YouTube Analytics, joins against
   `hsg_jobs`/`publish_results`, summarizes via Claude, writes to the
   `reports` table and `obsidian.writeReportNote()` (already implemented),
   updates `scoring_weights`.

5. Finally, wire up actual cron entrypoints for all three agents plus
   `reconcile.js`, and add basic tests/logging/retry-backoff that are
   currently missing.
