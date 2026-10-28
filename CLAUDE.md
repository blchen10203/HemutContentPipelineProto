# Hemut Content Pipeline

Generates review-ready ad/post text promoting Hemut's TMS (Hemut Command), Trxckwrld first. Output is drafts + export files. **Nothing is ever posted.**

## Two modes, one core
Both modes only decide *what to write about*. They each produce a `Brief`; everything after that is the same core pipeline:

`Brief -> angles -> draft -> validate -> retry (max 2) -> human review -> out/`

**Mode A: On-demand request.** A Hemut person asks for an ad about a specific thing (e.g. "Reddit-style ad about IFTA automation for 5-15 truck fleets"), optionally with notes and source links. The request is turned into a Brief and run through the core.

**Mode B: Automated.** **Seasonal** Briefs come from recurring problems and deadlines in trucking (produce season, winter weather, IFTA quarters, enforcement weeks, etc.). Active seasons boost how often Hemut's matching solution is advertised.
A weekly planner mixes seasonal + evergreen Briefs into a content plan.

## Hard rules
- Never post, publish, or call any write API for Trxckwrld, Meta, X, TikTok, or any platform. Export to `out/` only.
- Never push to the Trxckwrld repo. The Trxckwrld repo is NOT available yet: don't guess its schema or block on it. Use our own `TrxckwrldPost`; `export/trxckwrld.py` will map it once we have access.
- The knowledge base is ALWAYS loaded for every generation, in both modes. Facts come only from `knowledge/`.
- Mode A gap rule: if a request mentions something not covered by `claims.yaml` (a new feature, a deal, a number), STOP and return `needs_source` listing the unknown items. Never web-search or guess to fill the gap. If the requester attaches a source (URL or text), create *pending* claims with `requires_approval: true`; drafts using them are flagged for approval.
- Every number in generated copy must map to a `claims.yaml` entry or be flagged for human review. Never silently allowed.
- No testimonials, no invented quotes, no first-person customer/driver voice. Every post is visibly from Hemut (FTC fake-review rule; Hemut co-owns Trxckwrld).
- Product names only from `voice.yaml` (Command, Control, Hemi, Forge, Custom, Hemut Diesel). "Core" and "Reach" are retired names.
- Seasonal facts (dates, deadlines) are claims too: they need a source URL.
- Seasons and evergreen pillars only reach a Brief through `knowledge/bridge_map.yaml` (tag -> pain -> Hemut feature). No bridge, no Brief.
- Sensitive topics are never drafted automatically: crashes, deaths, injuries, layoffs, bankruptcies, immigration / English-proficiency / non-domiciled CDL enforcement, politics. Flag them `sensitivity: high`; the run stops there for a human.
- Secrets in `.env`, never committed.

## research/
research/ holds secondary research. It is never loaded into prompts and is never a source for claims.
research/ is kept locally and is gitignored, because it contains Hemut-internal notes and personal details.
A fact from research/ enters claims.yaml only after its primary source is snapshotted into
knowledge/sources/. If it can't be snapshotted, it stays out. Persona and bridge text drawn from
research/ must contain no numbers, no dates and no first-person or quoted speech.
Bryan Chen fact-checked research/hemut_market_brief_2026-10.md against its primary sources on 2026-10-26. Entries built
from it get verified_by: Bryan Chen (season windows) and checked: 2026-10-26 (claims). This does
not remove the need for a snapshot in knowledge/sources/ and does not change requires_approval.

## Layout
```
knowledge/       fact_sheet.md  claims.yaml  voice.yaml  audiences.yaml (reader personas)  seasonality.yaml  bridge_map.yaml  sources/ (dated snapshots)
                 loader.py (loads + checks claims.yaml / voice.yaml / audiences.yaml)   build_fact_sheet.py (fact_sheet.md is generated from claims.yaml)
                 pending_claims.yaml (Mode A claims from attached sources, requires_approval: true)
fetch_sources.py snapshots hemut.com pages into knowledge/sources/ (never overwrites a dated snapshot)
app.py           Streamlit thin shell over generate.py, modes/, planner.py, knowledge/ (local only)
brief_sources/   seasonal.py
export/          trxckwrld.py (adapter, later)
research/        secondary research, never loaded into prompts (see research/ rules)
assets/          local only, gitignored; brand files downloaded from hemut.com. Only photos/ is used: each finished ad gets a random photo from the reviewed list generate.PHOTO_NAMES (generate.pick_image), shown in the app and linked (not copied) from its draft-N.md; no folder, no photo. The testimonials/ photos show real people and customer brands: never use them without Hemut's written permission.
```

## Conventions
- Keep it boring: no vector DB, no agent framework.
- One Streamlit app (app.py) as a thin shell. It only calls functions in generate.py, modes/, planner.py, and knowledge/. No business logic, validation, or prompt text in app.py. Local only, no auth, never posts.
- Fact sheet goes into the system prompt whole (prompt caching). No retrieval for facts.
- Every run writes `meta.json`: mode, brief origin, wall-clock `duration_s` of the whole run, prompt versions, knowledge checked-dates, model, temperature or effort, validator results, and token usage and `duration_s` per API call with a run total (incl. `call_seconds`, which exceeds the wall time because drafts run in parallel) and $ estimate (prices in generate.PRICES).
- Schemas are the contract between modules. Don't change them without updating tests.

## Testing
- `tests/golden/` holds hand-written good and bad outputs. The validator must pass every good one and reject every bad one.
- Run `pytest` before any change to `validate.py` or `schemas.py` is considered done.
- Seasonal and planner code is tested with fixed dates, never live network calls.

## Status
Both modes run end to end through the Streamlit UI: knowledge/, schemas, validator + golden tests, generate.py core, Mode A, Mode B (seasonal + evergreen), app.py. There is no demo deadline any more.

## Next
- Pending claims from attached sources (knowledge/pending_claims.yaml)
- LLM judge, diversity check, source-similarity check
- Image templates
- Trxckwrld export adapter