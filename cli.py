"""Entry points. Writes drafts to out/runs/; never posts.

python cli.py request "<text>" [--notes "..."]
"""
import argparse
import sys

from dotenv import load_dotenv

from modes.request import run_request
from schemas import Request


def _progress(name: str, payload: dict) -> None:
    if name == "angles":
        print(f"{len(payload['angles'])} angles", file=sys.stderr)
    elif name == "draft":
        n = len(payload["violations"])
        print(f"angle {payload['angle'] + 1}, attempt {payload['attempt'] + 1}: {n or 'no'} violations", file=sys.stderr)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cli.py")
    sub = parser.add_subparsers(dest="command", required=True)
    req = sub.add_parser("request", help="Mode A: draft posts for one request")
    req.add_argument("text")
    req.add_argument("--notes")
    args = parser.parse_args(argv)

    load_dotenv()
    sys.stdout.reconfigure(errors="replace")  # claim wordings use en dashes; a cp1252/cp437 pipe must not crash
    result = run_request(Request(text=args.text, notes=args.notes), on_event=_progress)

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


if __name__ == "__main__":
    main()
