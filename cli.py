"""Entry points. Writes drafts to out/runs/; never posts.

python cli.py request "<text>" [--notes "..."]
python cli.py week [--date YYYY-MM-DD] [--dry-run]
"""
import argparse
import datetime
import sys

from dotenv import load_dotenv

from modes.request import run_request
from modes.scheduled import run_week
from planner import plan_week
from schemas import Request, RunResult


def _progress(name: str, payload: dict) -> None:
    if name == "angles":
        print(f"{len(payload['angles'])} angles", file=sys.stderr)
    elif name == "draft":
        n = len(payload["violations"])
        print(f"angle {payload['angle'] + 1}, attempt {payload['attempt'] + 1}: {n or 'no'} violations", file=sys.stderr)


def _print_result(result: RunResult) -> None:
    print(f"status: {result.status}")
    for item in result.needs_source:
        print(f"  needs source: {item}")
    for i, attempts in enumerate(result.drafts):
        last = attempts[-1]
        print(f"\n=== draft {i + 1} ({len(attempts)} attempt(s)) - angle: {result.angles[i].hook}")
        for a in attempts:
            print(f"  attempt {a.attempt + 1}: " + ("ok" if not a.violations else f"{len(a.violations)} violation(s)"))
            for v in a.violations:
                print(f"    - {v.code}: {v.message}")
        print()
        print(last.rendered_text or (last.raw_post.model_dump_json(indent=2) if last.raw_post else "(no post)"))
    print(f"\nrun folder: {result.run_dir}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cli.py")
    sub = parser.add_subparsers(dest="command", required=True)
    req = sub.add_parser("request", help="Mode A: draft posts for one request")
    req.add_argument("text")
    req.add_argument("--notes")
    week = sub.add_parser("week", help="Mode B: plan the week and draft each item")
    week.add_argument("--date", type=datetime.date.fromisoformat, default=datetime.date.today())
    week.add_argument("--dry-run", action="store_true", help="print the plan only; no API calls")
    args = parser.parse_args(argv)

    load_dotenv()
    sys.stdout.reconfigure(encoding="utf-8")  # pipes default to cp1252 on Windows, which garbles the en dash in "4–15"
    try:
        _run(args)
    except Exception as e:  # API/auth errors: the run folder is already written and named in the notes
        print(f"status: error\n{type(e).__name__}: {e}")
        for note in getattr(e, "__notes__", []):
            print(note)
        sys.exit(1)


def _run(args) -> None:
    if args.command == "request":
        _print_result(run_request(Request(text=args.text, notes=args.notes), on_event=_progress))
        return

    skipped: list[str] = []
    plan = plan_week(args.date, skipped=skipped)
    print(f"Plan for the week of {args.date}:")
    for n, item in enumerate(plan, 1):
        b = item.brief
        print(f"\n{n}. [{b.origin} / {b.format}] {b.origin_ref}: {b.pain}\n   feature: {b.hemut_feature}\n   why: {item.reason}")
    print("\nLeft out:" if skipped else "")
    for line in skipped:
        print(f"  - {line}")
    if not args.dry_run:
        for item, result in zip(plan, run_week(args.date, plan, on_event=_progress)):
            print(f"\n##### {item.brief.origin_ref}")
            _print_result(result)


if __name__ == "__main__":
    main()
