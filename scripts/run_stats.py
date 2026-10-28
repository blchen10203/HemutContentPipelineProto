"""Read-only report over run folders: per-run summary, where time and output tokens go, first-attempt violations.

Run: python scripts/run_stats.py [run_folder ...]   (no folders: every out/runs/*)
Never calls the API. Older runs without duration_s or usage just show "-" and are left out of those totals.
"""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = ["normalize", "angles", "draft-first-attempt", "draft-retry"]


def load(folders: list[Path]) -> list[dict]:
    metas = []
    for folder in folders:
        meta = folder / "meta.json"
        if meta.is_file():
            metas.append({"run": folder.name, **json.loads(meta.read_text(encoding="utf-8"))})
    return metas


def call_steps(meta: dict) -> list[str]:
    """Each logged call's step, with draft calls split into first attempts and retries. Draft calls are logged per angle
    in angle order, one per attempt, so they line up with the validator's attempt lists."""
    kinds = iter([("draft-first-attempt" if a["attempt"] == 0 else "draft-retry") for d in meta.get("validator", []) for a in d])
    calls = meta.get("usage", {}).get("calls", [])
    return [next(kinds, "draft-retry") if c["step"] == "draft" else c["step"] for c in calls]


def pass_attempt(draft: list[dict]) -> str:
    """'1', '2' or '3' for the attempt that first had no violations, else 'never'."""
    return next((str(a["attempt"] + 1) for a in draft if not a["violations"]), "never")


def _share(counter: Counter) -> str:
    total = sum(counter.values())
    return "  ".join(f"{k} {counter[k] / total:.0%}" for k in counter) if total else "-"


def report(metas: list[dict]) -> str:
    lines = [f"{'run':24} {'mode':4} {'status':17} {'secs':>6} {'calls':>5}  {'attempts/draft':14} {'usd':>7}"]
    for m in metas:
        total = m.get("usage", {}).get("total", {})
        secs = f"{m['duration_s']:.1f}" if "duration_s" in m else "-"
        usd = f"{total['usd_estimate']:.3f}" if total.get("usd_estimate") is not None else "-"
        attempts = ",".join(str(len(d)) for d in m.get("validator", [])) or "-"
        lines.append(f"{m['run']:24} {m.get('mode', '-'):4} {m['status']:17} {secs:>6} {total.get('calls', '-'):>5}  {attempts:14} {usd:>7}")

    timed = [m for m in metas if "duration_s" in m and "usage" in m]
    api_secs, out_tokens, wall = Counter(), Counter(), Counter()
    for m in timed:
        steps = call_steps(m)
        for step, call in zip(steps, m["usage"]["calls"]):
            api_secs[step] += call.get("duration_s", 0)
            out_tokens[step] += call["output_tokens"]
        serial = {s: sum(c.get("duration_s", 0) for c, k in zip(m["usage"]["calls"], steps) if k == s) for s in ("normalize", "angles")}
        wall.update(serial)
        wall["drafts (overlapping)"] += max(0.0, m["duration_s"] - sum(serial.values()))  # the rest of the wall clock

    drafts = [d for m in metas for d in m.get("validator", []) if d]
    first_codes = Counter(v["code"] for d in drafts for v in d[0]["violations"])
    passed = Counter(pass_attempt(d) for d in drafts)
    attempts = sum(len(d) for d in drafts)
    usd = [m["usage"]["total"]["usd_estimate"] for m in metas if m.get("usage", {}).get("total", {}).get("usd_estimate") is not None]

    lines += [
        "",
        f"Runs: {len(metas)}  timed: {len(timed)}  drafts: {len(drafts)}  total usd: {sum(usd):.2f}",
        f"Wall time by step (timed runs, {sum(m['duration_s'] for m in timed):.0f} s): {_share(wall)}",
        f"API call time by step (drafts overlap, so this sums past the wall time): {_share(Counter({s: api_secs[s] for s in STEPS}))}",
        f"Output tokens by step: {_share(Counter({s: out_tokens[s] for s in STEPS}))}",
        f"Average attempts per draft: {attempts / len(drafts):.2f}" if drafts else "Average attempts per draft: -",
        "Drafts passing on attempt: " + ("  ".join(f"{k} {passed[k] / len(drafts):.0%} ({passed[k]})" for k in ["1", "2", "3", "never"]) if drafts else "-"),
        "First-attempt violations by code: " + (", ".join(f"{c} {n}" for c, n in first_codes.most_common()) or "none"),
    ]
    return "\n".join(lines)


def main(args: list[str]) -> None:
    folders = [Path(a) for a in args] or sorted((ROOT / "out" / "runs").iterdir())
    print(report(load(folders)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
