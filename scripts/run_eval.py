"""Run every tests/eval/requests.yaml request through Mode A N times, then report needs_source accuracy and run_stats.

Run: python scripts/run_eval.py [--n 2] [--yes]
Calls the API (each run writes its folder to out/runs/ as usual). Prints an estimated cost and asks first unless --yes.
Progress goes to stderr, the report to stdout, so `> reports/eval_<date>.txt` keeps only the report.
"""
import argparse
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generate import OUT  # noqa: E402
from modes.request import run_request  # noqa: E402
from run_stats import load, report  # noqa: E402
from schemas import Request  # noqa: E402

REQUESTS = ROOT / "tests" / "eval" / "requests.yaml"
# shortcut: per-run cost from the Oct 27 eval (back-to-back runs share the prompt cache: drafted ~$0.13, needs_source ~$0.015;
# a lone cold run costs ~$0.32). Re-check if the prompts or the fact sheet grow.
USD_PER_RUN = {"drafts": 0.15, "needs_source": 0.02}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="run_eval.py")
    parser.add_argument("--n", type=int, default=2, help="runs per request")
    parser.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    args = parser.parse_args(argv)
    requests = yaml.safe_load(REQUESTS.read_text(encoding="utf-8"))

    estimate = args.n * sum(USD_PER_RUN[r["expect"]] for r in requests)
    print(f"{len(requests)} requests x {args.n} runs = {len(requests) * args.n} runs, estimated ${estimate:.2f}", file=sys.stderr)
    if not args.yes and input("Run them? [y/N] ").strip().lower() != "y":
        raise SystemExit("cancelled")

    load_dotenv(ROOT / ".env")
    folders, rows = [], []
    for i, r in enumerate(requests, 1):
        for n in range(args.n):
            before = set(OUT.iterdir()) if OUT.exists() else set()
            try:
                status = run_request(Request(text=r["text"], notes=r.get("notes"))).status
            except Exception as e:  # the run folder is still written; count it and go on
                status = f"error ({type(e).__name__})"
            folders += sorted(set(OUT.iterdir()) - before)
            got = "needs_source" if status == "needs_source" else "drafts"
            rows.append((r["expect"], got, status))
            print(f"[{i}/{len(requests)} run {n + 1}] {status}: {r['text']}", file=sys.stderr)

    right = sum(expect == got for expect, got, status in rows if not status.startswith("error"))
    lines = [f"Eval: {len(requests)} requests x {args.n} runs from {REQUESTS.relative_to(ROOT)}", ""]
    lines += [f"needs_source accuracy: {right}/{len(rows)} runs match expect"]
    lines += [f"  MISMATCH expect {expect}, got {status}: {r['text']}"
              for r, (expect, got, status) in zip([r for r in requests for _ in range(args.n)], rows) if expect != got]
    print("\n".join(lines) + "\n\n" + report(load(folders)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
