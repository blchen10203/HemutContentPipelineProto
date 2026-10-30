# Feature Screenshots Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ads show a Hemut Command screenshot of the feature they sell (random reviewed photo when there is none), the draft prompt knows what the screenshot shows, and Mode A can pick the feature from a dropdown.

**Architecture:** A new `knowledge/features.yaml` is the one list of features; bridge entries, `Brief`, `Request` and the image pick refer to a feature by id. `generate.pick_image` picks a feature screenshot that exists on disk, else today's photo, and returns the screenshot's `on_screen` note, which goes into the draft prompt. `app.py` only adds a selectbox and a table.

**Tech Stack:** Python 3, pydantic v2, PyYAML, Streamlit, pytest. Run tests with `.venv/Scripts/python -m pytest`.

**Spec:** `docs/superpowers/specs/2026-10-30-feature-screenshots-design.md`

## Global Constraints

- Nothing is posted; screenshots are linked, never copied into `out/`.
- Screenshots live in `assets/screenshots/` (gitignored with `assets/`). Tests never read the real `assets/`.
- A screenshot listed in `features.yaml` is a reviewed one: demo data only, no real customer, driver or broker names, no load or invoice numbers (stated in the file header).
- `on_screen`, `label` and `hemut_feature` of a feature pass `schemas._guidance_only` (no digits, month names, quotation marks, first person).
- Facts in copy still come only from claims; the validator does not change.
- Schemas are the contract: every schema change lands with its tests in the same task. Full `pytest` passes at the end of every task.
- Commit straight to `main` (no branches); every commit message ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Do not push.

## Review Focus

- Screenshot listed in `features.yaml` but its file is not on disk: the ad gets a random photo and no note, no error (Task 2 test).
- A `Brief.feature_id` that is no longer in `features.yaml` (old result re-shown in the app after the file changed): `pick_image` falls back to a photo, no `KeyError` (Task 2 test).
- `Request.feature_id` not in `features.yaml` (stale dropdown): `ValueError` naming the id, before any API call (Task 3 test).
- Feature picked, but the model returns another `feature_id` / `hemut_feature` / repeats a claim id: the picked feature wins and claim ids are deduped (Task 3 test).
- `Screenshot.file` with a folder part (`../x.png`, `sub/x.png`): rejected by the schema, so a listing can never point outside `assets/screenshots/` (Task 1 test).

Spec deviation, on purpose: the spec puts the "unknown claim id" and "unknown bridge `feature`" checks in the loader. The repo checks cross-file ids as tests on the real files (`test_every_bridge_claim_exists`), so this plan does the same; the loader checks only what one file can know (duplicate ids). Update the spec's Loader section to say so in Task 1's commit.

---

### Task 1: features.yaml, schemas, loader, bridge links

**Files:**
- Create: `knowledge/features.yaml`
- Modify: `schemas.py` (new `Screenshot`, `Feature`; `BridgeEntry.feature`; `Brief.feature_id`), `knowledge/loader.py` (`load_features`), `knowledge/bridge_map.yaml` (a `feature:` on every entry), `brief_sources/seasonal.py` (`bridge_brief`), `docs/superpowers/specs/2026-10-30-feature-screenshots-design.md` (Loader section)
- Test: `tests/test_loader.py`, `tests/test_knowledge_files.py`, `tests/test_schemas.py`, `tests/test_planner.py`

**Interfaces:**
- Produces:
  - `schemas.Screenshot(file: str, on_screen: str)`, `extra="forbid"`; `file` pattern `^[A-Za-z0-9][\w.-]*\.(png|jpe?g|webp)$` (a bare file name).
  - `schemas.Feature(id: str, label: str, hemut_feature: str, claim_ids: list[str], screenshots: list[Screenshot] = [])`, `extra="forbid"`, `id` pattern same as `Claim.id`; `label`, `hemut_feature` and every `on_screen` pass `_guidance_only`.
  - `BridgeEntry.feature: str` (required). `Brief.feature_id: str | None = None`.
  - `knowledge.loader.load_features(path: Path = ROOT / "knowledge" / "features.yaml") -> dict[str, Feature]`, raises `ValueError` on a duplicate id (same shape as `load_audiences`).
  - `bridge_brief()` sets `feature_id=bridge.feature`.

- [ ] **Step 1: Write the failing tests**

`tests/test_schemas.py`:
```python
def test_screenshot_file_is_a_bare_image_name():
    Screenshot(file="dispatch-board.png", on_screen="Dispatch board")
    for bad in ["../x.png", "sub/x.png", "x.gif", ".png"]:
        with pytest.raises(ValidationError):
            Screenshot(file=bad, on_screen="Dispatch board")

def test_on_screen_note_is_guidance_only():
    for bad in ["Shows 3 drivers", 'Says "on time"', "We show the board", "Due in April"]:
        with pytest.raises(ValidationError):
            Feature(id="f", label="F", hemut_feature="F", claim_ids=[], screenshots=[{"file": "a.png", "on_screen": bad}])
```
`tests/test_loader.py`: `test_duplicate_feature_id_fails` (two entries with `id: ifta` in a tmp `features.yaml` → `ValueError` matching `duplicate feature id 'ifta'`).
`tests/test_knowledge_files.py`:
```python
def test_real_features_load_and_their_claims_exist():
    claims, features = load_claims(), load_features()
    assert len(features) == 13
    assert len({f.label for f in features.values()}) == len(features)  # the app's dropdown maps a label back to its id
    missing = {(f.id, i) for f in features.values() for i in f.claim_ids if i not in claims}
    assert not missing, f"features.yaml uses claim ids not in claims.yaml: {sorted(missing)}"

def test_every_bridge_feature_exists():
    features = load_features()
    missing = {(b.tag, b.feature) for b in load_bridges() if b.feature not in features}
    assert not missing, f"bridge_map.yaml uses feature ids not in features.yaml: {sorted(missing)}"
```
`tests/test_planner.py`: `test_bridge_brief_carries_the_feature_id` (a `BridgeEntry(..., feature="detention")` through `bridge_brief` gives `brief.feature_id == "detention"`).

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_schemas.py tests/test_loader.py tests/test_knowledge_files.py tests/test_planner.py -q`
Expected: FAIL on import of `Screenshot` / `Feature` / `load_features`.

- [ ] **Step 3: Implement the schemas, `load_features`, and `bridge_brief`**

Add `feature="x"` to the `BridgeEntry(...)` constructors already in `tests/test_planner.py` (lines 25, 112-114) so they keep validating.

- [ ] **Step 4: Write `knowledge/features.yaml` and link `bridge_map.yaml`**

Header comment: what the file is, that listing a screenshot means a human reviewed it, the demo-data-only rule, that files live in `assets/screenshots/` and a missing file is skipped. Every entry has `screenshots: []` for now. The 13 features (`id`: `hemut_feature` [claim_ids] ← bridge tags that get `feature: <id>`):

| id | label | hemut_feature | claim_ids | bridge entries |
|---|---|---|---|---|
| ifta | IFTA quarterly reports | IFTA quarters built from the miles and fuel already in Command | hemi-desk-settlements-ifta, feature-back-office-in-plans | both entries of ifta-q1..q4 |
| live-tracking | Live tracking and late-load warnings | Customers warned before a load runs late, with live ETAs | hemi-desk-check-calls-tracking, feature-tracking | winter-weather, hurricane-season (tracking entries) |
| dispatch-board-hos | Dispatch board with hours of service | Hours of service shown on the dispatch board when a load is assigned | feature-hos-at-assignment, feature-dispatch-board | winter-weather, hurricane-season (HOS entries) |
| published-pricing | Published pricing and free trial | Every self-serve price is published, with a free trial and no card | prices-published, command-base-price, trial-days | evergreen-pricing |
| rate-cons-from-email | Rate confirmations from email | Rate confirmations that arrive by email become loads | feature-rate-cons-from-email, hemi-desk-inbox-rate-cons | evergreen-rate-cons |
| self-serve-setup | Self-serve setup | Self-serve setup, dispatching the same afternoon, able to run beside the old TMS | setup-same-afternoon, setup-what-comes-across, feature-beside-legacy-tms | evergreen-switching |
| detention | Detention tracking | Detention flagged while the truck waits, with dock time ready to bill | hemi-desk-detention | evergreen-detention |
| hemut-diesel | Hemut Diesel fuel card | Hemut Diesel, a fuel card with fleet discounts and nationwide coverage | product-hemut-diesel | evergreen-diesel-prices |
| collections | Collections and short pays | Overdue invoices chased, with short pays and deductions surfaced | hemi-desk-payments-collections | evergreen-short-pays-collections (collections entry) |
| pods-to-invoices | PODs to invoices | PODs chased until they are in, and delivered loads become invoices | hemi-desk-pod-paperwork, hemi-desk-billing | evergreen-short-pays-collections (POD entry) |
| driver-ranking | Driver ranking for each load | On Command Pro, drivers ranked for each load with hours of service in view | hemi-desk-dispatch, feature-driver-ranking, feature-hos-at-assignment | evergreen-tight-capacity |
| expiring-documents | Expiring document reminders | Expiring documents turn into a renewal task before they lapse | feature-compliance-expiry, hemi-desk-pod-paperwork | evergreen-expiring-documents |
| backhauls | Backhaul finding | On Command Pro, backhauls found before a truck sits | hemi-desk-dispatch | evergreen-empty-miles |

Bridge entries keep their own `hemut_feature` wording and `claim_ids` (incl. the `ifta-qN-due` claims). Add one line to the bridge_map header: `feature: the features.yaml id this angle sells; it picks the ad's screenshot.`

Edit the spec's Loader section: duplicate ids fail in the loader; unknown claim ids and bridge feature ids are caught by `tests/test_knowledge_files.py` on the real files.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add knowledge/features.yaml knowledge/bridge_map.yaml knowledge/loader.py schemas.py brief_sources/seasonal.py tests docs/superpowers/specs/2026-10-30-feature-screenshots-design.md
git commit -m "Add features.yaml; bridge entries and Briefs name their feature"
```

---

### Task 2: Screenshot pick, draft prompt note, meta.json

**Files:**
- Modify: `generate.py` (`SCREENSHOTS`, `pick_image`, `_generate`, `_write_run`), `prompts/draft.txt`
- Test: `tests/conftest.py`, `tests/test_generate.py`

**Interfaces:**
- Consumes: `load_features()`, `Feature`, `Brief.feature_id` (Task 1).
- Produces:
  - `generate.SCREENSHOTS = ROOT / "assets" / "screenshots"`.
  - `generate.pick_image(run_id: str, angle: int, feature_id: str | None = None) -> tuple[Path, str | None] | None`: `(path, on_screen)` for a screenshot, `(path, None)` for a photo, `None` for neither. Module-level `from knowledge.loader import load_features` so tests can monkeypatch `generate.load_features`.

- [ ] **Step 1: Fixtures**

`tests/conftest.py`: the autouse fixture also points `generate.SCREENSHOTS` at an empty tmp folder. New fixture `screenshots(monkeypatch, tmp_path_factory)`: writes `TINY_PNG` to `board-a.png` and `board-b.png` in a tmp folder, sets `generate.SCREENSHOTS` to it, and monkeypatches `generate.load_features` to return `{"dispatch-board-hos": Feature(id="dispatch-board-hos", label="Board", hemut_feature="Board", claim_ids=[], screenshots=[{"file": "board-a.png", "on_screen": "Board A"}, {"file": "board-b.png", "on_screen": "Board B"}, {"file": "missing.png", "on_screen": "Missing"}]), "ifta": Feature(id="ifta", label="IFTA", hemut_feature="IFTA", claim_ids=[], screenshots=[{"file": "missing.png", "on_screen": "Missing"}])}`; returns the folder.

- [ ] **Step 2: Write the failing tests** (`tests/test_generate.py`)

```python
def test_feature_screenshot_beats_photo_and_brings_its_note(photos, screenshots):
    picks = {generate.pick_image(f"run-{n}", a, "dispatch-board-hos") for n in range(20) for a in range(3)}
    assert {(p.name, note) for p, note in picks} == {("board-a.png", "Board A"), ("board-b.png", "Board B")}  # never the missing file

def test_no_screenshot_falls_back_to_a_photo_without_note(photos, screenshots):
    for feature_id in [None, "ifta", "removed-feature"]:  # no feature, a feature whose only screenshot is not on disk, an id no longer listed
        path, note = generate.pick_image("run-1", 0, feature_id)
        assert path.parent == photos and note is None

def test_draft_prompt_gets_the_screenshot_note(tmp_path, photos, screenshots, serial):  # serial: calls[1 + i] is angle i
    client = FakeClient(ANGLES, GOOD, GOOD, GOOD)
    result, _ = run(client, tmp_path, BRIEF.model_copy(update={"feature_id": "dispatch-board-hos"}))
    for i, call in enumerate(client.calls[1:]):
        _, note = generate.pick_image(result.run_id, i, "dispatch-board-hos")
        assert f"The ad shows this Hemut screenshot: {note}" in call["messages"][0]["content"]

def test_draft_prompt_says_not_to_refer_to_a_photo(tmp_path, photos):
    client = FakeClient(ANGLES, GOOD, GOOD, GOOD)
    run(client, tmp_path)
    assert all(generate.NO_SCREENSHOT in c["messages"][0]["content"] for c in client.calls[1:])

def test_meta_records_each_finished_ads_image(tmp_path, photos, screenshots, serial):
    result, _ = run(FakeClient(ANGLES, GOOD, BAD), tmp_path, BRIEF.model_copy(update={"feature_id": "dispatch-board-hos"}))
    images = json.loads((Path(result.run_dir) / "meta.json").read_text(encoding="utf-8"))["images"]
    assert images[0]["image_kind"] == "screenshot" and images[0]["image"] in {"board-a.png", "board-b.png"}
    assert images[1:] == [None, None]  # failed drafts get no image
```
Update the three existing photo tests (lines 300-320) to the tuple return: `path, note = generate.pick_image(...)`, `note is None`; `test_pick_image_is_random_but_stable` compares `{p.name for p, _ in picks}`.

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_generate.py -q`
Expected: FAIL (`pick_image` returns a `Path`, no `NO_SCREENSHOT`, no `images` in meta).

- [ ] **Step 4: Implement**

- `pick_image`: one `random.Random(f"{run_id}:{angle}")`; feature from `load_features().get(feature_id)` (unknown id → no feature); choose among that feature's screenshots whose file is in `SCREENSHOTS`, else among `PHOTO_NAMES` files as now. Replace the old `shortcut:` comment, since topic matching now exists.
- Two constants beside `PHOTO_NAMES`, exact copy:
  - `SCREENSHOT_NOTE = "The ad shows this Hemut screenshot: {note} The copy may point at what it shows; facts still come only from the fact sheet."`
  - `NO_SCREENSHOT = "The ad shows a brand photo or no image. Do not refer to the image."`
- `_generate`: per angle, `image = pick_image(result.run_id, i, brief.feature_id)`, and pass `screen=` the note line (or `NO_SCREENSHOT` when `image` is `None` or its note is `None`) to `load_prompt("draft.txt", ...)`.
- `prompts/draft.txt`: after the `{angle}` block add:
  ```
  Image (background for you, the writer):
  {screen}
  ```
- `_write_run`: the existing per-draft loop already picks the image; pass `result.brief.feature_id` (brief may be `None` on a failed Mode A run, then `None`), link `image[0]`, and collect `meta["images"]`: per draft `{"image": path.name, "image_kind": "screenshot" if note else "photo"}` for a finished ad with an image, else `None`. Write `meta.json` after that loop (move the `meta.json` write below it, or build `images` first).

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add generate.py prompts/draft.txt tests/conftest.py tests/test_generate.py
git commit -m "Pick the feature's screenshot for each ad and tell the drafter what it shows"
```

---

### Task 3: Mode A feature pick

**Files:**
- Modify: `schemas.py` (`Request.feature_id`), `modes/request.py` (`request_to_brief`), `prompts/normalize.txt`
- Test: `tests/test_request.py`

**Interfaces:**
- Consumes: `load_features()`, `Feature` (Task 1).
- Produces: `Request.feature_id: str | None = None`; `request_to_brief(request, claims, *, voice=None, audiences=None, features: dict[str, Feature] | None = None, client=None, usage=None) -> Brief`.

- [ ] **Step 1: Write the failing tests** (`tests/test_request.py`)

```python
def test_picked_feature_is_forced_onto_the_brief():
    client = FakeClient(brief_reply(feature_id="live-tracking", hemut_feature="something else", claim_ids=["feature-dispatch-board", "command-base-price"]))
    brief = request_to_brief(Request(text="Short ad for dispatchers", feature_id="dispatch-board-hos"), CLAIMS, client=client)
    assert brief.feature_id == "dispatch-board-hos"
    assert brief.hemut_feature == "Hours of service shown on the dispatch board when a load is assigned"
    assert brief.claim_ids == ["feature-dispatch-board", "command-base-price", "feature-hos-at-assignment"]  # model's first, deduped
    assert "Dispatch board with hours of service" in client.calls[0]["messages"][0]["content"]

def test_without_a_pick_the_model_may_name_a_real_feature_or_none():
    client = FakeClient(brief_reply(feature_id="ifta"))
    assert request_to_brief(Request(text="IFTA post"), CLAIMS, client=client).feature_id == "ifta"
    assert request_to_brief(Request(text="IFTA post"), CLAIMS, client=FakeClient(brief_reply())).feature_id is None
    schema = client.calls[0]["output_config"]["format"]["schema"]["properties"]["feature_id"]  # a made-up id cannot pass
    assert {e for option in schema["anyOf"] for e in option.get("enum", [])} == set(load_features())
    assert {"type": "null"} in schema["anyOf"]

def test_unknown_picked_feature_fails_before_any_call():
    client = FakeClient(brief_reply())
    with pytest.raises(ValueError, match="'gone'"):
        request_to_brief(Request(text="x", feature_id="gone"), CLAIMS, client=client)
    assert client.calls == []
```
(Same technique as the existing `test_request_maps_to_a_real_persona_id`. If `anthropic.transform_schema` renders the optional Literal differently from `anyOf`, adjust only the path into the schema; the two assertions stay.)

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_request.py -q`
Expected: FAIL (`Request` has no `feature_id`).

- [ ] **Step 3: Implement**

- `request_to_brief`: load `features` if `None`; if `request.feature_id` is set and not in `features`, `raise ValueError(f"Request feature_id {request.feature_id!r} is not in knowledge/features.yaml")` first. Response shape adds `feature_id=(Literal[tuple(features)] | None, None)`. After the call, when a feature was picked: `feature_id`, `hemut_feature` from the feature, `claim_ids = list(dict.fromkeys(<model's known ids> + feature.claim_ids))`; the unknown-id gap logic stays as is.
- `prompts/normalize.txt`: new bullet after `hemut_feature`: `- feature_id: see "Feature" below.` and a block at the end:
  ```
  Feature:
  {feature}
  ```
  `{feature}` is, when picked: `The requester picked this feature. Set feature_id to <id> and build the brief around it: <label>: <hemut_feature>`; otherwise: `Set feature_id to the id of the feature below that the request is about, or leave it empty if none fits.` followed by one line per feature, `- <id>: <label>` (same style as `{personas}`).

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add schemas.py modes/request.py prompts/normalize.txt tests/test_request.py
git commit -m "Mode A: a request can pick the feature it sells"
```

---

### Task 4: App dropdown, features table, docs

**Files:**
- Modify: `app.py`, `CLAUDE.md`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `load_features()` (Task 1), `pick_image(run_id, angle, feature_id) -> tuple[Path, str | None] | None` (Task 2), `Request.feature_id` (Task 3).

- [ ] **Step 1: Write the failing tests** (`tests/test_app.py`)

In `test_app_runs_both_modes_and_keeps_results`, change the knowledge-tab assertion to `len(at.dataframe) == 3`. New test:
```python
def test_feature_dropdown_reaches_the_request(monkeypatch):
    seen = []
    monkeypatch.setattr(modes.request, "run_request", lambda request, on_event: seen.append(request) or RESULT)
    at = AppTest.from_file(str(Path(__file__).parent.parent / "app.py"), default_timeout=30).run()
    box = at.selectbox[0]
    assert box.options[0] == "Any (from the text)" and "Dispatch board with hours of service" in box.options
    box.select("Dispatch board with hours of service").run()
    at.text_area[0].input("Short ad for dispatchers").run()
    click(at, "Run")
    assert seen[-1].feature_id == "dispatch-board-hos"
    at.selectbox[0].select("Any (from the text)").run()
    click(at, "Run")
    assert seen[-1].feature_id is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/Scripts/python -m pytest tests/test_app.py -q`
Expected: FAIL (no selectbox, two dataframes).

- [ ] **Step 3: Implement in `app.py`**

- Request tab, above the text area: `st.selectbox("Feature (optional)", ["Any (from the text)", *labels])` with plain label strings (AppTest's `select()` takes the option value, so no `format_func`); map the chosen label back with `{f.label: f.id for f in features.values()}.get(choice)` and pass it as `Request(..., feature_id=...)`.
- `show_result`: `image = pick_image(result.run_id, i, result.brief.feature_id)`; `show_ad(..., image[0] if image else None)`.
- Knowledge tab, between Seasons and Claims: `st.subheader("Features")` and a dataframe with `id`, `label`, `claims` (comma-joined), `screenshots` as `"<found on disk> of <listed>"` (use `generate.SCREENSHOTS`).

- [ ] **Step 4: Update `CLAUDE.md`**

Layout: add `features.yaml` to the `knowledge/` line. Assets note: each finished ad gets its feature's screenshot from `assets/screenshots/` (listed in `knowledge/features.yaml`, demo data only, no real customer, driver or broker names), else a random photo from `generate.PHOTO_NAMES`; still linked, not copied. Hard rules: `Seasons and evergreen pillars only reach a Brief through bridge_map.yaml` gets `(tag -> pain -> feature -> claims)`.

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -q`
Expected: all pass.

- [ ] **Step 6: Check it in the app**

Run `streamlit run app.py` locally, confirm the dropdown lists 13 features plus "Any", and the Knowledge tab shows "0 of 0" screenshots for every feature. Drop one demo PNG into `assets/screenshots/`, list it on one feature, and confirm the table shows "1 of 1" (revert the listing afterwards unless it is a real reviewed screenshot).

- [ ] **Step 7: Commit**

```bash
git add app.py CLAUDE.md tests/test_app.py
git commit -m "App: feature dropdown for requests, features table in Knowledge"
```
