# Hemut Content Pipeline

Turns a short brief into review-ready static content promoting Hemut's TMS (Hemut Command), Trxckwrld first. Output is drafts + export files. **Nothing is ever posted.**

## Hard rules
- Never post, publish, or call any write API for Trxckwrld, Meta, or any social platform. Export to `out/` only.
- Never push to the Trxckwrld repo. Read its post model; produce JSON in that shape.
- The Trxckwrld repo is NOT available yet. Don't guess its schema or block on it. Use our own `TrxckwrldPost` model; a separate `export/trxckwrld.py` adapter will map it to their format once we have access.
- Facts come only from `knowledge/`. If a fact isn't in `fact_sheet.md` or `claims.yaml`, it doesn't go in copy.
- Every number in generated copy must map to a `claims.yaml` entry or be flagged for human review. Never silently allowed.
- No testimonials, no invented quotes, no first-person customer/driver voice. Every post is visibly from Hemut (FTC fake-review rule; Hemut co-owns Trxckwrld).
- Product names only from `voice.yaml` (Command, Control, Hemi, Forge, Custom, Hemut Diesel). "Core" and "Reach" are not current names.
- Secrets in `.env`, never committed.

## Layout
```
knowledge/   fact_sheet.md  claims.yaml  voice.yaml
schemas.py   Pydantic v2 models: Brief, TrxckwrldPost, StatCard
validate.py  deterministic checks (numbers, names, banned words, voice, CTA/UTM)
generate.py  brief -> structured brief -> angles -> draft -> validate -> retry (max 2)
prompts/     normalize.txt  angles.txt  draft.txt   (versioned files, not inline strings)
tests/       golden/ (good + bad examples)  test_validate.py
out/runs/<timestamp>/   drafts + meta.json
```

## Conventions
- Python 3.11+, Pydantic v2, pytest. Keep it boring: no vector DB, no agent framework, no web UI until the core loop works.
- Fact sheet goes into the system prompt whole (prompt caching). No retrieval for facts.
- Every run writes `meta.json`: prompt versions, fact sheet checked-date, model, temperature, validator results.
- Schemas are the contract between modules. Don't change them without updating tests.

## Testing
- `tests/golden/` holds hand-written good and bad outputs. The validator must pass every good one and reject every bad one.
- Run `pytest` before any change to `validate.py` or `schemas.py` is considered done.

## Build order (Oct 31 demo)
0. Project skeleton: pyproject.toml, folder layout, .gitignore, .env.example, one passing test
1. knowledge/ files (claims built from https://hemut.com/llms-full.txt and /pricing)
2. schemas.py (Trxckwrld text post + stat card only)
3. validate.py + golden tests
4. generate.py with retry-on-validator-errors
5. CLI review: show draft, claims used, validator result; approve/reject to out/

Mid-November (not now): LLM judge, diversity check, image templates, review dashboard, Trxckwrld JSON export, `calendar.yaml` of sourced trucking deadlines that auto-create briefs.

After November (not now): reactive trend detection (Trxckwrld data, news RSS, Federal Register). Trends only feed briefs via a bridge map (trend → pain → feature); trend facts get registry entries with expiry dates; sensitive topics (crashes, deaths, layoffs, immigration/ELP/CDL enforcement) are never auto-briefed.