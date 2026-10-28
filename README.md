# Hemut Content Pipeline

Turns a short brief into review-ready static content for Hemut Command. Drafts and exports only; nothing is ever posted. See `CLAUDE.md` for rules and status.

## Setup

Requires Python 3.11+.

```sh
python -m venv .venv
.venv\Scripts\activate        # Windows; on macOS/Linux: source .venv/bin/activate
pip install -e .
cp .env.example .env          # then set ANTHROPIC_API_KEY
pytest
```
