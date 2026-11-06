# Add-feature form: design

Date: 2026-11-06. Status: approved in chat, awaiting spec review.

## Goal

Hemut keeps shipping features. A Hemut engineer or product person, with no knowledge of this repo, should be able to
add a new feature in a few minutes so that the next Mode A request and the next Mode B week can write ads about it.

Today adding a feature means hand-editing up to five knowledge files (a source snapshot, `claims.yaml`,
`features.yaml`, `bridge_map.yaml`, `screenshot_captions.yaml`), rebuilding `fact_sheet.md` and running pytest.

## Decisions (from the user)

| Question | Decision |
|---|---|
| Where features are added | A form in the Streamlit app (Knowledge tab) |
| What backs the facts | A hemut.com page URL (snapshotted) plus "verified by Name (Role)" |
| When ads can use it | Right away, once the save passes its checks; an engineer commits the files later |
| Mode B | Yes: the form also creates an evergreen bridge entry |
| Ad wordings | Free text, 1 to 3 (no word-for-word check against the snapshot) |

Known risk of free-text wordings with instant go-live: a wrong number or overstated claim typed into the form reaches
ads with only the "verified by" name behind it. The snapshot is kept, so a word-for-word check can be added later.

## The form

In the Knowledge tab, an `st.form` titled "Add feature":

| Field | Example | Becomes |
|---|---|---|
| Feature name | Voice agents for check calls | `features.yaml` `label` |
| What it does (one line, for the writer) | Phone agents that place driver check calls | `features.yaml` and bridge `hemut_feature` |
| hemut.com page URL | https://hemut.com/voice-agents | snapshot `knowledge/sources/<id>_<YYYY-MM-DD>.txt` (+ `.html` for HTML pages) |
| Ad wordings (1 to 3, free text) | Hemi places the driver check calls for you | `claims.yaml` entries `feature-<id>-1..3`, `type: feature` |
| Verified by | Jane Doe (Product Manager) | `verified_by` on each new claim |
| What pain does it fix? (one sentence) | Dispatchers lose hours chasing drivers for check calls | bridge `pain` |
| Which readers? (checkboxes from `audiences.yaml`) | dispatcher, fleet-owner | bridge `audiences` |
| Screenshot (optional upload) and caption | | `assets/screenshots/<id>.<ext>`, `screenshot_captions.yaml`, the feature's `screenshots` |

The feature id is a slug of the name (`voice-agents-for-check-calls`). A screenshot needs a caption and an on-screen
description; the caption is reused as `on_screen` so the form asks for one line, not two.

## What Save does

`knowledge/add_feature.add_feature(f: NewFeature) -> str` (returns the feature id):

1. Validate `NewFeature` (see Checks). Refuse an id that already exists in `features.yaml`, a claim id that exists,
   or a snapshot `<id>_<today>.*` that exists (dated snapshots are never overwritten).
2. Snapshot the URL with `fetch_sources.snapshot(name, url)`. Nothing has been written to the YAML files yet, so a
   fetch failure stops here.
3. Save the screenshot, if any.
4. Back up the knowledge files it will touch, in memory: `claims.yaml`, `features.yaml`, `bridge_map.yaml`,
   `screenshot_captions.yaml`, `fact_sheet.md`.
5. Append one text block to each YAML file (appending keeps every existing comment). New claims carry
   `source_url`, `source_snapshot`, `checked: <today>`, `verified_by`, `requires_approval: false`. The bridge entry is
   `tag: evergreen-<id>`, `pain`, `hemut_feature`, `claim_ids` (the new claims), `feature: <id>`, `audiences`.
6. Rebuild `fact_sheet.md` (`knowledge.build_fact_sheet`).
7. Reload with every loader (`load_claims`, `load_features`, `load_bridges`, `load_audiences`, `load_captions`) and
   re-run the knowledge-file checks on the new claims.
8. On any failure in steps 3 to 7: restore the backed-up files byte for byte, delete the new snapshot and screenshot,
   raise `ValueError` naming the field. On success the app shows: "Live: the next Mode A request and Mode B week can
   use it. Commit the changed knowledge files when convenient."

Nothing caches knowledge files: `generate.py`, the planner and the Mode A dropdown reload them per run, so no restart
is needed.

## Checks (in `NewFeature` and `add_feature`)

- URL scheme is https and host is `hemut.com` or a subdomain of it.
- 1 to 3 wordings, none empty.
- Each wording passes the validator's own helpers: `_banned_words`, `_retired_names`, `_competitor_names` from
  `validate.py` (same rules the knowledge-file tests apply to every claim).
- `verified_by` matches `Name (Role)`: non-empty text, then a non-empty role in parentheses.
- Pain, "what it does" and caption pass `schemas._guidance_only` (no digits, quotes, month names or first-person
  words). Wordings are copy, not guidance, so they may contain numbers.
- At least one audience, each an id from `audiences.yaml`.
- Screenshot, if given: png, jpg or webp.

## Code changes

- `fetch_sources.py`: extract `snapshot(name, url, client=None) -> Path` from `main()`; `main()` calls it, CLI
  behaviour unchanged. It keeps the "never overwrite a dated snapshot" rule.
- `knowledge/add_feature.py` (new): `NewFeature` (Pydantic, `extra="forbid"`), `add_feature`, `slugify`.
  Shortcut comment: no lock, the app is local and single-user; two simultaneous saves could interleave.
- `schemas.py`: `Claim.verified_by: str | None = None`. Existing claims unchanged.
- `app.py`: the form in the Knowledge tab. It builds `NewFeature`, calls `add_feature`, shows success or the
  `ValueError` / `ValidationError` text. No logic or prompt text.
- `CLAUDE.md`: one line under Layout for `knowledge/add_feature.py`; one line under Hard rules noting that the form
  is the supported way to add a feature and that its URL + verified_by is the sign-off.

## Testing

No live network calls; fixed data.

- `tests/test_add_feature.py` (new), on a temp copy of `knowledge/` with `snapshot()` faked:
  - Happy path: snapshot, claims (with `verified_by`), feature, `evergreen-<id>` bridge and caption are written; every
    loader loads; `plan_week` can pick the new pillar; the Mode A dropdown labels include it.
  - One rejection case each: non-hemut.com URL, no wordings, four wordings, banned word, retired product name,
    competitor name, digit in pain, `verified_by` without a role, no audiences, duplicate name.
  - Rollback: force a failure after writing; every knowledge file matches its original bytes; new snapshot and
    screenshot are gone.
  - Existing header comments in the YAML files survive an add.
- `tests/test_fetch_sources.py`: `snapshot()` writes `.txt` (and `.html` for HTML) from a fake response; refuses an
  existing dated snapshot.
- `tests/test_app.py`: submitting the form calls `add_feature` with the fields and shows success; an error shows its
  message, not a traceback.
- Full `pytest` passes, including the golden validator tests (the validator is not changed).

## Out of scope

- Editing or deleting a feature through the form (engineers edit the YAML).
- Pending claims from non-hemut.com sources (`pending_claims.yaml` stays on the Next list).
- Committing to git from the app.
- Seasonal bridges (seasons stay hand-curated).
