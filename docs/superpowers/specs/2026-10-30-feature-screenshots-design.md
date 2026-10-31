# Feature screenshots instead of random photos

Date: 2026-10-30. Status: approved design, not built.

## Goal

Each finished ad shows a Hemut Command screenshot of the feature it sells, and its copy can point at what the
screenshot shows. Mode A gets a dropdown to pick the feature. Until screenshots exist (none do yet), everything
behaves as today: a random reviewed brand photo.

## Decisions

- A **feature** is a new first-class knowledge entry (`knowledge/features.yaml`). Bridge entries, Briefs, the Mode A
  dropdown and the image pick all point at a feature id. (Rejected: matching screenshots by claim overlap, which is
  fuzzy because feature claims repeat across bridge entries; listing screenshots on bridge entries, which repeats them
  across the IFTA quarters.)
- Mode A dropdown picks a **feature** (optional; "Any" keeps free-text behaviour).
- No screenshot for a feature: **random photo, as today** (`PHOTO_NAMES`).
- Each screenshot carries an **`on_screen` note** the drafter reads, so copy may refer to the image. The note is
  writer guidance only, never a source of facts.

## Data

`knowledge/features.yaml`, one entry per feature as the product shows it (about 13 to start, from the 14 distinct
`hemut_feature` lines in `bridge_map.yaml`; both IFTA wordings share one feature):

```yaml
- id: dispatch-board-hos
  label: Dispatch board with hours of service          # dropdown text
  hemut_feature: Hours of service shown on the dispatch board when a load is assigned
  claim_ids: [feature-hos-at-assignment, feature-dispatch-board]
  screenshots:                                         # optional; [] until screenshots exist
    - file: dispatch-board.png                         # in assets/screenshots/
      on_screen: Dispatch board; each driver row shows hours left before a load is assigned
```

File header rules:
- Listing a screenshot means a human reviewed it (same idea as `generate.PHOTO_NAMES`).
- Screenshots show demo data only: no real customer, driver or broker names, no load or invoice numbers.
- Screenshots live in `assets/screenshots/` (local only, gitignored with the rest of `assets/`). A listed file that
  is not on disk is skipped silently.

## Schema changes (`schemas.py`)

- New `Screenshot(file: str, on_screen: str)`. `on_screen` passes `_guidance_only` (no digits, month names,
  quotation marks or first-person text).
- New `Feature(id, label, hemut_feature, claim_ids, screenshots: list[Screenshot] = [])`, `extra="forbid"`, id pattern
  as `Claim.id`. `hemut_feature` passes `_guidance_only`, as on `BridgeEntry`.
- `BridgeEntry.feature: str` (required). Its own `hemut_feature` text stays: that is the angle's wording.
- `Brief.feature_id: str | None = None`.
- `Request.feature_id: str | None = None`.

## Loader (`knowledge/loader.py`)

`load_features() -> dict[str, Feature]`. Fails on a duplicate id. Unknown claim ids and bridge `feature` ids are caught
by `tests/test_knowledge_files.py` on the real files.

## Flow

**Mode B.** `brief_sources/seasonal.bridge_brief()` sets `Brief.feature_id = bridge.feature`. Planner unchanged.

**Mode A.** `modes/request.request_to_brief()`:
- `Request.feature_id` set: the normalize prompt is told the picked feature (label + `hemut_feature`). After the call,
  the Brief is forced to `feature_id`, the feature's `hemut_feature`, and `claim_ids` = model's ids plus the
  feature's ids (deduped, order kept). The gap rule is unchanged: anything else the text asks for that no claim covers
  still lands in `needs_source`.
- `Request.feature_id` unset: the normalize response schema allows `feature_id` as `Literal[<feature ids>] | None`
  (same technique as `audience_id`), so a free-text request can still match a feature and its screenshot.

**Image pick (`generate.py`).** `pick_image(run_id, angle, feature_id=None)` returns `(path, on_screen | None)` or
`None`:
1. The feature's listed screenshots that exist in `SCREENSHOTS` (`assets/screenshots/`): seeded random pick by
   `f"{run_id}:{angle}"`, so the app, the run folder and the draft prompt agree.
2. Else today's seeded random pick from `PHOTO_NAMES`, with no note.
3. Else `None`.

The pick happens per angle before drafting. `prompts/draft.txt` gets a `{screen}` slot:
- screenshot: "The ad will show this screenshot: {on_screen}. The copy may point at what it shows; facts still come
  only from claims."
- photo or none: "The ad shows a brand photo or no image; do not refer to the image."

The validator is unchanged. The prompt hash change is recorded by the existing `prompt_versions` in `meta.json`.

## App (`app.py`, thin shell)

- Request tab: `st.selectbox("Feature (optional)", ...)` above the text box, options "Any (from the text)" plus each
  feature's `label` from `load_features()`. The chosen id goes into `Request(feature_id=...)`.
- `show_ad` unchanged; it gets the path from the new `pick_image`.
- Knowledge tab: a "Features" table with label, claim ids, and screenshots listed / found on disk.

## Run output

- `draft-N.md` links (does not copy) the picked image, as today.
- `meta.json` records per draft `image` (file name or null) and `image_kind` (`screenshot`, `photo` or null).

## Tests

Fixed data, no network, never the real `assets/` (extend the `no_photos` / `photos` fixtures in `tests/conftest.py`
with a screenshots folder).

- Loader: unknown claim id, unknown bridge `feature`, duplicate feature id, `on_screen` with a digit or quotation mark
  each fail; the real `features.yaml` loads and every bridge entry resolves.
- `pick_image`: screenshot chosen when its file exists; photo fallback when the screenshot is listed but missing or
  the feature has none; `None` with neither folder; stable for the same run and angle; spreads across a feature's
  screenshots over many runs.
- Mode A: a picked feature is forced onto the Brief even when the model returns another; with "Any" the model may
  return a real id or null, and a made-up id is rejected by the response schema.
- Draft prompt contains the `on_screen` note for a screenshot and the "do not refer" line otherwise.
- `meta.json` has `image` and `image_kind` per finished draft.
- App: the selectbox lists the features and the chosen id reaches `run_request`.
- Existing photo tests updated to the new `pick_image` return value. Full `pytest` passes.

## Out of scope

- Image templates (overlays, crops, text on image).
- Checking that copy matches the screenshot (belongs with the planned LLM judge).
- Planner "same feature twice in a week" switching to feature ids.
- Taking the screenshots themselves.

## Docs

`CLAUDE.md`: add `features.yaml` to the knowledge layout, `assets/screenshots/` to the assets note, and the
demo-data-only rule.
