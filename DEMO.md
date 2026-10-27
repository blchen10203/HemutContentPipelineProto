# Demo script (Oct 31, about 10 minutes)

A local demo of both modes through the Streamlit app. Nothing is posted anywhere: every run only writes files to `out/runs/<timestamp>/`.

## Setup (the day before)

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```sh
uv venv
uv pip install --python .venv/Scripts/python.exe -e .   # macOS/Linux: .venv/bin/python
cp .env.example .env                                   # then set ANTHROPIC_API_KEY=sk-ant-...
.venv/Scripts/pytest -q                                # all tests pass, no network
.venv/Scripts/streamlit run app.py                     # opens http://localhost:8501
```

The first time Streamlit runs on a machine it asks for an email address and waits. Press Enter to skip it, or add `--server.headless true` to the command (then open http://localhost:8501 yourself).

Every command calls the venv's own tools, so there is no activate step (PowerShell blocks `Activate.ps1` by default). On macOS/Linux use `.venv/bin/` instead of `.venv/Scripts/`.

## Morning of: pre-run everything (fallback)

A request takes about 70 seconds and "Draft all" runs five briefs back to back (about 5 minutes). Run every demo item once in the morning, in the app or with the CLI:

```sh
.venv/Scripts/python cli.py request "Reddit-style ad about IFTA automation for 5-15 truck fleets"
.venv/Scripts/python cli.py request "Post about Hemut's new fuel card with 50% off in November"
.venv/Scripts/python cli.py week --date 2026-10-31
```

Each run prints its run folder. Keep those folders open in a file browser or editor. If the API is slow or down during the demo, show the pre-run `draft-*.md` and `meta.json` files instead of running live.

**Don't click anything while a run is going.** Any click in Streamlit restarts the script and aborts the run. The run folder is still written, with status `error`, but the drafts on screen are gone.

## 1. Mode A happy path (3 min)

Tab **Request (Mode A)**. Type:

> Reddit-style ad about IFTA automation for 5-15 truck fleets

Click **Run**. While it runs (about 70s), the screen shows only a progress line counting finished ads ("Drafting: 2 ads ready"). When it finishes, only the finished ads show. The intermediate steps stay off screen but are all saved in the run folder (see below). Drafts that never pass the checks are not shown. Talk over it:

- Behind the progress line, the request becomes a Brief (audience in the requester's words, the closest reader persona, pain, Hemut feature, format, the claim ids that cover it). The persona's pains, objections and tone go into the angle and draft prompts.
- Three angles, one draft each. Every draft goes through the deterministic validator. A draft with a violation is sent back with the violations, at most twice.

When it finishes, point at one draft:

- Every number and product fact in it was inserted from `knowledge/claims.yaml` by claim id. The model never writes a number itself, and the validator rejects any number that didn't come from a claim.
- It is visibly from Hemut, with the Trxckwrld co-ownership disclosed. No testimonials, no customer voice.
- The CTA link carries UTM tags.

## 2. Mode A gap (1 min)

Same tab. Type:

> Post about Hemut's new fuel card with 50% off in November

Click **Run**. One call, a few seconds. Result: **Needs a source before anything is drafted**, listing what no claim covers (the 50% / November deal). No angles, no drafts. It does not web-search or guess. A Hemut person has to supply a source first.

## 3. Mode B weekly plan (4 min)

Tab **Weekly plan (Mode B)**. Week of **2026-10-31** (the default). Click **Plan**. This makes no API calls. Each item is headed by the problem it addresses. Walk through the plan:

1. **"The office rebuilds the IFTA return by hand…"** (Seasonal, Reddit post): the IFTA Q3 return is due Oct 31. The reason line names who checked the season dates against the source. Drafts can state the due date because it is a claim (`ifta-q3-due`, from iftach.org), and the claim always says "or the next business day when that falls on a weekend or holiday". That matters this year: Oct 31, 2026 is a Saturday.
2. **"Storm delays push loads late…"** (Seasonal): Atlantic hurricane season runs through Nov 30 (source: NOAA's hurricane center). Like IFTA, its reason line names who checked the dates.
3. **"Trucks wait at the dock for hours…"** (Trend, Social post): the detention trend, from the frozen trend fixture. The reason shows how many items back it and when the trend card expires.
4. and 5. **Evergreen** (Short ads): published pricing and rate confirmations retyped by hand.

Each _Why_ line ends with the reader the item is written for (from `knowledge/audiences.yaml`). Readers rotate so a week repeats one as little as it can. This week only three of the four personas fit these angles, so two repeat.

Then the **Left out** list, one line per thing the planner refused:

- `check-call-overload`: the trend card **expired** Oct 28. An expired trend never becomes a Brief.
- `english-proficiency-enforcement`: **sensitive**. Never auto-briefed; a human decides.
- `truck-parking`: **no bridge**. A trend reaches a Brief only through `bridge_map.yaml` (trend to pain to Hemut feature). No bridge, no Brief.
- `evergreen-switching`: **no slot left this week**. Five slots, and active seasons and trends come first.

Click **Draft all**. Results appear one brief at a time (about 5 minutes total). Talk through the first one while the rest run. If time is short, open the pre-run week folders instead.

## 4. What to point out (2 min)

- **Nothing is posted.** There is no posting code and no platform write API. Output is files in `out/runs/`.
- **Every number traces to a claim.** Open `knowledge/claims.yaml` (or the **Knowledge** tab) and find the claim behind a price in a draft. It has a source URL, a dated snapshot in `knowledge/sources/` and a checked date.
- **Approval badges.** A draft that uses a claim marked `requires_approval` (ROI numbers, competitor facts, customer names) shows an orange **Approval needed** badge. The flag is worked out from the claims, never taken from the model.
- **The run folder.** The newest folder in `out/runs/` (named by date and time). Open it:
  - `draft-N.md`: the rendered draft, ready for a human to review.
  - `meta.json`: mode, brief origin, model, effort, prompt versions (content hashes), knowledge checked dates, and every validator result for every attempt.
  - `result.json`: the full Brief, angles and attempts.
