# Add-feature form Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A form in the Streamlit app's Knowledge tab lets a Hemut engineer or product person add a new feature, which the next Mode A request and Mode B week can use with no restart.

**Architecture:** `fetch_sources.snapshot()` (extracted from `main()`) saves the hemut.com page. `knowledge/add_feature.py` holds a validated `NewFeature` model and `add_feature()`, which appends YAML blocks to the knowledge files, rebuilds the fact sheet, reloads everything and restores the files byte for byte on any failure. `app.py` only draws the form and calls `add_feature`.

**Tech Stack:** Python 3.11, Pydantic v2, PyYAML, httpx, Streamlit 1.66, pytest (+ `streamlit.testing.v1.AppTest`).

**Spec:** `docs/superpowers/specs/2026-11-06-add-feature-form-design.md`

## Global Constraints

- Never post or call any write API; the form only writes local files under `knowledge/` and `assets/screenshots/`.
- No live network calls in tests; `snapshot()` and httpx are faked.
- `app.py` holds no business logic, validation or prompt text: it builds `NewFeature`, calls `add_feature`, shows the result.
- Dated snapshots in `knowledge/sources/` are never overwritten.
- Appending keeps every existing comment in the YAML files; never rewrite a whole YAML file with `yaml.safe_dump`.
- New claims: `type: feature`, ids `feature-<id>-1..3`, `checked: <today>`, `requires_approval: false`, `verified_by: <Name (Role)>`.
- Bridge entry tag is `evergreen-<id>`; its `claim_ids` are the new claims; its `feature` is `<id>`.
- Product names only from `voice.yaml`; wordings must pass `validate._banned_words`, `_retired_names`, `_competitor_names` (all must return `[]`).
- Pain, "what it does", label and caption pass `schemas._guidance_only` (no digits, quotes, month names, first person).
- Run full `pytest` before calling a task done (CLAUDE.md: required for any `schemas.py` change).
- Commits go straight to `main` (repo convention), ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. Lookalike hosts (`hemut.com.evil.io`, `nothemut.com`, `http://hemut.com`) must be rejected; only `https` on `hemut.com` or `*.hemut.com`. Test in Task 2.
2. Form text with YAML-special characters (`: `, `#`, leading `- `, `"`, smart quotes, non-ASCII) must round-trip exactly through the appended YAML. Test in Task 3.
3. The form has three wording boxes and most people fill one: blank and whitespace-only boxes are dropped, the rest stripped. Test in Task 2.
4. A feature name that slugifies to nothing (`"!!!"`) gives a clear error, not an empty id. Test in Task 2.
5. A fetch that fails (HTTP error, timeout) writes nothing and the app shows the message, not a traceback. Tests in Task 3 and Task 4.

---

### Task 1: `fetch_sources.snapshot()`

**Files:**
- Modify: `fetch_sources.py` (`main()`, lines 62-80)
- Test: `tests/test_fetch_sources.py`

**Interfaces:**
- Produces: `snapshot(name: str, url: str, *, out: Path = OUT, today: datetime.date | None = None, client: httpx.Client | None = None) -> Path` returns the `.txt` path. Raises `FileExistsError` if `<name>_<today>.*` exists in `out`; raises `httpx.HTTPError` on fetch failure (status checked with `raise_for_status`). HTML responses also write `<name>_<today>.html`. `client=None` opens its own `httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": "Mozilla/5.0"})`.

- [ ] **Step 1: Write the failing tests** in `tests/test_fetch_sources.py`

```python
class FakeClient:
    def __init__(self, text, content_type): self.r = httpx.Response(200, text=text, headers={"content-type": content_type}, request=httpx.Request("GET", "https://hemut.com/x"))
    def get(self, url): return self.r

def test_snapshot_writes_text_and_html(tmp_path):
    day = datetime.date(2026, 11, 6)
    path = fetch_sources.snapshot("voice", "https://hemut.com/x", out=tmp_path, today=day,
                                  client=FakeClient("<p>Hi</p>", "text/html"))
    assert path == tmp_path / "voice_2026-11-06.txt" and path.read_text(encoding="utf-8") == "Hi\n"
    assert (tmp_path / "voice_2026-11-06.html").read_text() == "<p>Hi</p>"

def test_snapshot_refuses_existing_dated_file(tmp_path):
    (tmp_path / "voice_2026-11-06.txt").write_text("cited")
    with pytest.raises(FileExistsError):
        fetch_sources.snapshot("voice", "https://hemut.com/x", out=tmp_path, today=datetime.date(2026, 11, 6),
                               client=FakeClient("new", "text/plain"))
    assert (tmp_path / "voice_2026-11-06.txt").read_text() == "cited"
```

- [ ] **Step 2: Run them to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_fetch_sources.py -v`
Expected: the two new tests FAIL with `AttributeError: module 'fetch_sources' has no attribute 'snapshot'`.

- [ ] **Step 3: Implement `snapshot()`** and make `main()` loop over `snapshot(name, url, client=client)` inside its existing `httpx.Client`. Keep `main()`'s up-front `SystemExit` check for existing snapshots and its print line, so the existing CLI tests pass unchanged.

- [ ] **Step 4: Run the file**

Run: `.venv/Scripts/python.exe -m pytest tests/test_fetch_sources.py -v`
Expected: all PASS (old and new).

- [ ] **Step 5: Commit**

```bash
git add fetch_sources.py tests/test_fetch_sources.py
git commit -m "Extract snapshot() from fetch_sources.main for reuse"
```

---

### Task 2: `Claim.verified_by` and the `NewFeature` model

**Files:**
- Modify: `schemas.py` (`Claim`, after `requires_approval`)
- Create: `knowledge/add_feature.py`
- Test: `tests/test_add_feature.py` (new)

**Interfaces:**
- Produces:
  - `Claim.verified_by: str | None = None`
  - `slugify(name: str) -> str`: lowercase, runs of non `[a-z0-9]` become `-`, strip `-`. `"Voice agents for check calls"` -> `"voice-agents-for-check-calls"`.
  - `class NewFeature(BaseModel)`, `extra="forbid"`, fields: `name: str`, `does: str`, `url: str`, `wordings: list[str]`, `verified_by: str`, `pain: str`, `audiences: list[str]`, `screenshot: bytes | None = None`, `screenshot_ext: str | None = None` (`"png" | "jpg" | "jpeg" | "webp"`), `caption: str | None = None`. Property `id -> str` = `slugify(name)`.
  - Field rules (raise `ValueError` naming the field): strip all strings; drop blank wordings, then require 1 to 3; `url` is `https` with host `hemut.com` or ending `.hemut.com` (`urllib.parse.urlsplit`); `verified_by` matches `^[^()]+\(\s*[^()]+\s*\)$`; `name`, `does`, `pain`, `caption` pass `_guidance_only`; `id` non-empty; `audiences` non-empty; `screenshot` given requires `screenshot_ext` and `caption`; `caption` given requires `screenshot`.
  - Audience ids and voice checks need the knowledge files, so they live in `add_feature` (Task 3), not the model.

- [ ] **Step 1: Write the failing tests** in `tests/test_add_feature.py`

```python
GOOD = dict(name="Voice agents for check calls", does="Phone agents that place driver check calls",
            url="https://hemut.com/voice-agents", wordings=["Hemi places the driver check calls for you", " ", ""],
            verified_by="Jane Doe (Product Manager)", pain="Dispatchers lose hours chasing drivers for check calls",
            audiences=["dispatcher"])

def nf(**over): return NewFeature(**(GOOD | over))

def test_good_feature_strips_and_drops_blank_wordings():
    f = nf()
    assert f.id == "voice-agents-for-check-calls" and f.wordings == ["Hemi places the driver check calls for you"]

@pytest.mark.parametrize("over, field", [
    ({"url": "http://hemut.com/x"}, "url"), ({"url": "https://hemut.com.evil.io/x"}, "url"),
    ({"url": "https://nothemut.com/x"}, "url"), ({"wordings": ["", " "]}, "wordings"),
    ({"wordings": ["a", "b", "c", "d"]}, "wordings"), ({"verified_by": "Jane Doe"}, "verified_by"),
    ({"pain": "Dispatchers lose 3 hours"}, "pain"), ({"audiences": []}, "audiences"),
    ({"name": "!!!"}, "name"), ({"screenshot": b"x", "screenshot_ext": "png"}, "caption"),
])
def test_bad_fields_are_rejected(over, field):
    with pytest.raises(ValidationError, match=field):
        nf(**over)

def test_subdomain_url_is_allowed():
    assert nf(url="https://command.hemut.com/x").url == "https://command.hemut.com/x"

def test_claim_takes_verified_by():
    assert Claim.model_validate({**VALID_CLAIM, "verified_by": "Jane Doe (PM)"}).verified_by == "Jane Doe (PM)"
```

`VALID_CLAIM` is a minimal valid feature claim dict defined at the top of the test file (`type: feature`, string value, one phrasing, any source fields).

- [ ] **Step 2: Run to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_add_feature.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'knowledge.add_feature'`.

- [ ] **Step 3: Add `Claim.verified_by`, and write `slugify` and `NewFeature`** in `knowledge/add_feature.py`, using `field_validator`/`model_validator` per the rules above.

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add schemas.py knowledge/add_feature.py tests/test_add_feature.py
git commit -m "Add NewFeature model and Claim.verified_by"
```

---

### Task 3: `add_feature()`: write, check, roll back

**Files:**
- Modify: `knowledge/add_feature.py`
- Test: `tests/test_add_feature.py`

**Interfaces:**
- Consumes: `fetch_sources.snapshot` (Task 1), `NewFeature` (Task 2), loaders in `knowledge/loader.py` (all take a `path`; `load_claims(path, root=root)`), `knowledge.build_fact_sheet.render(claims) -> str`, `validate._banned_words/_retired_names/_competitor_names(text, voice) -> list[Violation]`.
- Import `snapshot` and every loader by name into `knowledge/add_feature.py` (`from fetch_sources import snapshot`, `from knowledge.loader import load_claims, ...`) so tests can monkeypatch them there.
- Produces: `add_feature(f: NewFeature, *, root: Path = ROOT, today: datetime.date | None = None) -> str` returns the feature id; raises `ValueError` with a message naming the field on any failure. All paths derive from `root`: `root/knowledge/{claims,features,bridge_map,screenshot_captions}.yaml`, `root/knowledge/fact_sheet.md`, `root/knowledge/sources/`, `root/assets/screenshots/`.

Order of work (from the spec, "What Save does"): checks that need knowledge files (audience ids exist in `load_audiences`; wording voice checks; feature id, claim ids `feature-<id>-N` and `evergreen-<id>` tag not taken), then `snapshot(f.id, f.url, out=sources, today=today)` (wrap `httpx.HTTPError`/`FileExistsError` as `ValueError("url: ...")`), then screenshot to `assets/screenshots/<id>.<ext>` (refuse if it exists), then back up the five files as bytes, append, rebuild fact sheet, reload all five loaders, then verify the new feature, claims and bridge are present. On any exception after the snapshot: restore the bytes, unlink the new snapshot files (`<id>_<today>.*`) and screenshot, re-raise as `ValueError`.

Each appended block is `"\n" + yaml.safe_dump([entry], sort_keys=False, allow_unicode=True)` for list files, and `yaml.safe_dump({file: caption}, allow_unicode=True)` for captions. The feature entry's screenshot is `{file: <id>.<ext>, on_screen: caption}`.

- [ ] **Step 1: Write the failing tests**

Fixture `kb(tmp_path, monkeypatch)`: `shutil.copytree(ROOT / "knowledge", tmp_path / "knowledge")`, create `tmp_path / "assets" / "screenshots"`, and monkeypatch `knowledge.add_feature.snapshot` with a fake that writes `"<page>"` to `out / f"{name}_{today}.txt"` and returns the path. `DAY = datetime.date(2026, 11, 6)`.

```python
def test_happy_path_goes_live(kb):
    fid = add_feature(nf(screenshot=TINY_PNG, screenshot_ext="png", caption="Agents place calls for you"), root=kb, today=DAY)
    k = kb / "knowledge"
    claims = load_claims(k / "claims.yaml", root=kb)
    assert claims[f"feature-{fid}-1"].verified_by == "Jane Doe (Product Manager)"
    assert claims[f"feature-{fid}-1"].source_snapshot == f"knowledge/sources/{fid}_2026-11-06.txt"
    assert load_features(k / "features.yaml")[fid].screenshots[0].file == f"{fid}.png"
    assert any(b.tag == f"evergreen-{fid}" for b in load_bridges(k / "bridge_map.yaml"))
    assert load_captions(k / "screenshot_captions.yaml")[f"{fid}.png"] == "Agents place calls for you"
    assert f"feature-{fid}-1" in (k / "fact_sheet.md").read_text(encoding="utf-8")
    picked = {i.brief.feature_id for w in range(12) for i in plan_week(DAY + datetime.timedelta(weeks=w), seasons=[],
              bridges=load_bridges(k / "bridge_map.yaml"), audiences=load_audiences(k / "audiences.yaml"))}
    assert fid in picked

def test_yaml_special_characters_round_trip(kb):
    text = 'Hemi: books loads # fast - "quoted" ’smart’ café'
    fid = add_feature(nf(wordings=[text]), root=kb, today=DAY)
    assert load_claims(kb / "knowledge" / "claims.yaml", root=kb)[f"feature-{fid}-1"].phrasings == [text]

@pytest.mark.parametrize("over", [{"wordings": ["Guaranteed on-time loads"]}, {"wordings": ["Built on Hemut Core"]},
                                  {"audiences": ["no-such-reader"]}])
def test_voice_and_audience_checks_write_nothing(kb, over):
    before = snapshot_bytes(kb)
    with pytest.raises(ValueError):
        add_feature(nf(**over), root=kb, today=DAY)
    assert snapshot_bytes(kb) == before

def test_duplicate_name_is_rejected(kb):
    add_feature(nf(), root=kb, today=DAY)
    with pytest.raises(ValueError, match="name"):
        add_feature(nf(), root=kb, today=DAY + datetime.timedelta(days=1))

def test_failure_after_writing_restores_every_file(kb, monkeypatch):
    before = snapshot_bytes(kb)
    monkeypatch.setattr(knowledge.add_feature, "load_bridges", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    with pytest.raises(ValueError, match="boom"):
        add_feature(nf(screenshot=TINY_PNG, screenshot_ext="png", caption="Agents place calls for you"), root=kb, today=DAY)
    assert snapshot_bytes(kb) == before  # knowledge files, sources and screenshots all as they were

def test_fetch_failure_writes_nothing(kb, monkeypatch):
    before = snapshot_bytes(kb)
    def fail(*a, **k): raise httpx.ConnectTimeout("timed out")
    monkeypatch.setattr(knowledge.add_feature, "snapshot", fail)
    with pytest.raises(ValueError, match="url"):
        add_feature(nf(), root=kb, today=DAY)
    assert snapshot_bytes(kb) == before

def test_header_comments_survive(kb):
    first = (kb / "knowledge" / "features.yaml").read_text(encoding="utf-8").splitlines()[0]
    add_feature(nf(), root=kb, today=DAY)
    assert (kb / "knowledge" / "features.yaml").read_text(encoding="utf-8").splitlines()[0] == first
```

`snapshot_bytes(root) -> dict[str, bytes]` maps every file under `root/knowledge` and `root/assets` to its bytes. `TINY_PNG` comes from `tests/conftest.py`. The audience id `dispatcher` in `GOOD` must exist in `knowledge/audiences.yaml`; if it does not, use one that does.

- [ ] **Step 2: Run to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_add_feature.py -v`
Expected: the Task 3 tests FAIL with `ImportError: cannot import name 'add_feature'`.

- [ ] **Step 3: Implement `add_feature`** as described above. Add the comment `# shortcut: no lock, the app is local and single-user; two saves at once could interleave. Add a file lock if it is ever shared.`

- [ ] **Step 4: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all PASS, and `git status` shows no change to the real `knowledge/` files.

- [ ] **Step 5: Commit**

```bash
git add knowledge/add_feature.py tests/test_add_feature.py
git commit -m "add_feature writes a new feature into the knowledge files, with rollback"
```

---

### Task 4: The form in the app, and docs

**Files:**
- Modify: `app.py` (Knowledge tab, after the Claims table)
- Modify: `CLAUDE.md` (Layout and Hard rules)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `NewFeature`, `add_feature` (Tasks 2 and 3), `load_audiences()`.

Form (`st.form("add_feature")`, subheader "Add feature"): `text_input` "Feature name"; `text_input` "What it does (one line)"; `text_input` "hemut.com page URL"; three `text_input` "Ad wording 1/2/3"; `text_input` "Verified by (Name (Role))"; `text_input` "What pain does it fix? (one sentence, no numbers)"; `multiselect` "Which readers?" over `load_audiences()` labels mapped back to ids; `file_uploader` "Screenshot (optional)" types png/jpg/jpeg/webp; `text_input` "Caption (if screenshot)"; submit button "Add feature". On submit: build `NewFeature` and call `add_feature`. Catch `ValidationError` (show `st.error(e.errors()[0]["msg"])`, as the Request tab does) and `ValueError` (`st.error(str(e))`). On success: `st.success("Live: the next Mode A request and Mode B week can use it. Commit the changed knowledge files when convenient.")`.

- [ ] **Step 1: Write the failing tests** in `tests/test_app.py`

```python
def fill_feature_form(at):
    at.text_input(key="nf_name").input("Voice agents for check calls")  # give each widget a key=nf_*
    ...  # fill does, url, wording 1, verified_by, pain; select one audience
    return click(at, "Add feature")

def test_add_feature_form_calls_add_feature(monkeypatch):
    got = []
    monkeypatch.setattr(knowledge.add_feature, "add_feature", lambda f, **k: got.append(f) or f.id)
    at = fill_feature_form(AppTest.from_file(APP, default_timeout=30).run())
    assert got[0].wordings == ["Hemi places the driver check calls for you"]
    assert any("Live:" in s.value for s in at.success)

def test_add_feature_error_shows_message(monkeypatch):
    def fail(f, **k): raise ValueError("url: could not fetch the page")
    monkeypatch.setattr(knowledge.add_feature, "add_feature", fail)
    at = fill_feature_form(AppTest.from_file(APP, default_timeout=30).run())
    assert any("could not fetch" in e.value for e in at.error) and not at.exception
```

`app.py` must call `knowledge.add_feature.add_feature(...)` through the module (`import knowledge.add_feature as add_feature_mod` or equivalent) so the monkeypatch takes effect; widget keys are `nf_name`, `nf_does`, `nf_url`, `nf_w1`, `nf_w2`, `nf_w3`, `nf_verified`, `nf_pain`, `nf_aud`, `nf_shot`, `nf_caption`.

- [ ] **Step 2: Run to see them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_app.py -k add_feature -v`
Expected: FAIL (no widget with key `nf_name`).

- [ ] **Step 3: Add the form to `app.py`** per the description above.

- [ ] **Step 4: Update `CLAUDE.md`**: under Layout add `add_feature.py (the app's Add feature form: snapshots a hemut.com URL, appends claims/feature/bridge/caption, rolls back on failure)` to the `knowledge/` line; under Hard rules add `- New features are added through the app's Add feature form (knowledge/add_feature.py). Its hemut.com snapshot plus verified_by "Name (Role)" is the sign-off; wordings are free text, so the verifier owns their accuracy.`

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: all PASS.

- [ ] **Step 6: Restart the app and check the form renders**

Stop and start the `app` preview server (code changed outside `app.py`), open the Knowledge tab, confirm the "Add feature" form shows all fields. Do not submit (it would fetch hemut.com and write real knowledge files).

- [ ] **Step 7: Commit**

```bash
git add app.py tests/test_app.py CLAUDE.md
git commit -m "Add feature form in the Knowledge tab"
```
