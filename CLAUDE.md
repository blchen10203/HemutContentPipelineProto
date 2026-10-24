# Hemut Content Pipeline

Generates review-ready ad/post text promoting Hemut's TMS (Hemut Command), Trxckwrld first. Output is drafts + export files. **Nothing is ever posted.**

## Two modes, one core
Both modes only decide *what to write about*. They each produce a `Brief`; everything after that is the same core pipeline:

`Brief -> angles -> draft -> validate -> retry (max 2) -> human review -> out/`

**Mode A: On-demand request.** A Hemut person asks for an ad about a specific thing (e.g. "Reddit-style ad about IFTA automation for 5-15 truck fleets"), optionally with notes and source links. The request is turned into a Brief and run through the core.

**Mode B: Automated.** Brief sources create Briefs on a schedule:
1. **Seasonal**: recurring problems and deadlines in trucking (peak season, produce season, winter weather, IFTA quarters, enforcement weeks, etc.). Active seasons boost how often Hemut's matching solution is advertised.
2. **Trends**: what's being talked about now in trucker spaces, trucking news, and social platforms.
A weekly planner mixes seasonal + trend + evergreen Briefs into a content plan.

## Hard rules
- Never post, publish, or call any write API for Trxckwrld, Meta, X, TikTok, or any platform. Export to `out/` only.
- Never push to the Trxckwrld repo. The Trxckwrld repo is NOT available yet: don't guess its schema or block on it. Use our own `TrxckwrldPost`; `export/trxckwrld.py` will map it once we have access.
- The knowledge base is ALWAYS loaded for every generation, in both modes. Facts come only from `knowledge/`.
- Mode A gap rule: if a request mentions something not covered by `claims.yaml` (a new feature, a deal, a number), STOP and return `needs_source` listing the unknown items. Never web-search or guess to fill the gap. If the requester attaches a source (URL or text), create *pending* claims with `requires_approval: true`; drafts using them are flagged for approval.
- Every number in generated copy must map to a `claims.yaml` entry or be flagged for human review. Never silently allowed.
- No testimonials, no invented quotes, no first-person customer/driver voice. Every post is visibly from Hemut (FTC fake-review rule; Hemut co-owns Trxckwrld).
- Product names only from `voice.yaml` (Command, Control, Hemi, Forge, Custom, Hemut Diesel). "Core" and "Reach" are retired names.
- Seasonal and trend facts (dates, deadlines, "rates are spiking") are claims too: they need a source URL, and trend claims need `expires_at`. Drafts built on expired claims are invalid.
- Trends only reach a Brief through `knowledge/bridge_map.yaml` (trend -> pain -> Hemut feature). No bridge, no Brief.
- Sensitive topics are never auto-briefed: crashes, deaths, injuries, layoffs, bankruptcies, immigration / English-proficiency / non-domiciled CDL enforcement, politics. Flag them `sensitivity: high` for a human.
- Social trends inform topic, hook structure, and format ("pattern cards") only. Never copy or closely paraphrase a source post or image; drafts must stay below a similarity threshold to their source items.
- No unofficial scraping of Instagram, TikTok, X, or Facebook. Use official APIs only, and only once access is approved. Until then those sources are stubs.
- Secrets in `.env`, never committed.

## Layout
```
knowledge/       fact_sheet.md  claims.yaml  voice.yaml  seasonality.yaml  bridge_map.yaml  sources/ (dated snapshots)
                 loader.py (loads + checks claims.yaml / voice.yaml)   build_fact_sheet.py (fact_sheet.md is generated from claims.yaml)
                 pending_claims.yaml (Mode A claims from attached sources, requires_approval: true)
fetch_sources.py snapshots hemut.com pages into knowledge/sources/ (never overwrites a dated snapshot)
schemas.py       Pydantic v2: Claim, VoiceRules, Request, Brief (origin: request|seasonal|trend|evergreen), TrxckwrldPost, StatCard, Violation, RunResult, SeasonWindow, BridgeEntry, TrendItem, TrendCard, PlanItem
validate.py      deterministic checks (numbers, names, banned words, voice, CTA/UTM, expired claims, source similarity)
generate.py      core: run_brief(): Brief -> angles -> draft -> validate -> retry, with an on_event progress callback
app.py           Streamlit thin shell over generate.py, modes/, planner.py, knowledge/ (local only)
prompts/         versioned prompt files, not inline strings
modes/           request.py (Mode A)   scheduled.py (Mode B)
brief_sources/   seasonal.py   trends/ (base.py, fixture.py, rss.py, federal_register.py, reddit.py, trxckwrld.py, instagram.py, tiktok.py, x.py)
planner.py       weekly mix: pillar targets + active seasons + top trend cards, avoids repeated angles
export/          trxckwrld.py (adapter, later)
cli.py           entry points for both modes + review
tests/           golden/  fixtures/ (frozen dated data, e.g. the demo trend fixture) + unit tests
out/runs/<timestamp>/   drafts + meta.json
```

## Conventions
- Python 3.11+, Pydantic v2, pytest. Keep it boring: no vector DB, no agent framework.
- One Streamlit app (app.py) as a thin shell. It only calls functions in generate.py, modes/, planner.py, and knowledge/. No business logic, validation, or prompt text in app.py. Local only, no auth, never posts.
- Fact sheet goes into the system prompt whole (prompt caching). No retrieval for facts.
- Every run writes `meta.json`: mode, brief origin, prompt versions, knowledge checked-dates, model, temperature or effort, validator results.
- Every trend source implements one interface (`brief_sources/trends/base.py`), so adding or swapping a platform touches one file.
- Schemas are the contract between modules. Don't change them without updating tests.

## Testing
- `tests/golden/` holds hand-written good and bad outputs. The validator must pass every good one and reject every bad one.
- Run `pytest` before any change to `validate.py` or `schemas.py` is considered done.
- Trend and seasonal code is tested with fixture data, never live network calls.

## Build order
Oct 31 demo: a local demo of BOTH modes through a thin Streamlit UI. Project skeleton is done.
1. knowledge/: voice.yaml, generated fact_sheet.md (claims.yaml is done)
2. schemas.py: Request, Brief, TrxckwrldPost, StatCard, Violation, RunResult, SeasonWindow, BridgeEntry, TrendItem, TrendCard, PlanItem
3. validate.py + golden tests
4. generate.py core: run_brief() with retry and an on_event progress callback
5. Mode A: modes/request.py (function first) + minimal cli.py
6. Mode B lite: seasonality.yaml + bridge_map.yaml (human-verified), seasonal source, ONE frozen dated trend fixture, planner.py, modes/scheduled.py
7. Streamlit UI (app.py)
8. Demo hardening + DEMO.md

Cut list if behind, in this order:
1. Knowledge tab in the UI
2. Trend fixture (Mode B goes seasonal + evergreen only)
3. Pending claims from attached sources

## After the demo
- Live trend sources: RSS, Federal Register, Reddit, Trxckwrld (when access), Instagram, X, TikTok (official APIs only, once access is approved)
- Clustering/scoring of trends
- LLM judge, diversity check, source-similarity check
- Image templates
- Trxckwrld export adapter