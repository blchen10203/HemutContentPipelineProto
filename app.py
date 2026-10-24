"""Streamlit thin shell over generate.py, modes/, planner.py and knowledge/. Local only; never posts.

Run: streamlit run app.py
"""
import datetime

import streamlit as st
from dotenv import load_dotenv
from pydantic import ValidationError

from knowledge.loader import load_claims, load_seasons
from modes.request import run_request
from modes.scheduled import run_week
from planner import plan_week
from schemas import Request, RunResult

load_dotenv()
st.set_page_config(page_title="Hemut content pipeline", layout="wide")
st.title("Hemut content pipeline")
st.caption("Drafts for human review only. Nothing is posted.")


def on_event_for(status):
    def on_event(name: str, payload: dict) -> None:
        if name == "brief":
            status.write(f"**Brief** ({payload['origin']}, {payload['format']}): {payload['pain']} → {payload['hemut_feature']}")
        elif name == "angles":
            status.write("**Angles:** " + " · ".join(a["hook"] for a in payload["angles"]))
        elif name == "draft":
            n = len(payload["violations"])
            status.write(f"Angle {payload['angle'] + 1}, attempt {payload['attempt'] + 1}: {n or 'no'} violations")
        elif name == "done":
            status.write(f"Done: {payload['status']}")
    return on_event


def show_result(result: RunResult) -> None:
    if result.needs_source:
        st.warning("**Needs a source before anything is drafted.** Nothing in claims.yaml covers:\n\n"
                   + "\n".join(f"- {item}" for item in result.needs_source))
    elif result.status == "blocked_sensitive":
        st.error("**Blocked: sensitive topic.** A human decides whether to write about this.")
    for i, attempts in enumerate(result.drafts):
        last = attempts[-1]
        with st.container(border=True):
            st.markdown(f"**Draft {i + 1}** · angle: {result.angles[i].hook}")
            if last.raw_post and last.raw_post.requires_approval:
                st.badge("Approval needed", color="orange")
            for a in attempts:
                st.write(f"Attempt {a.attempt + 1}: " + ("passed" if not a.violations else f"{len(a.violations)} violation(s)"))
                for v in a.violations:
                    st.write(f"- `{v.code}` {v.message}")
            # st.text, not markdown: "$99 ... $29" would render as LaTeX
            st.text(last.rendered_text or (last.raw_post.model_dump_json(indent=2) if last.raw_post else "(no post)"))
    st.caption(f"Run folder: {result.run_dir}")


def run_with_status(label: str, job):
    """Run job(on_event) inside a status box; show errors (and the run folder note) instead of a traceback."""
    status = st.status(label, expanded=True)
    try:
        out = job(on_event_for(status))
    except Exception as e:
        status.update(label=f"{label}: failed", state="error")
        st.error(f"{type(e).__name__}: {e}\n\n" + "\n".join(getattr(e, "__notes__", [])))
        return None
    status.update(label=f"{label}: done", state="complete", expanded=False)
    return out


request_tab, week_tab, knowledge_tab = st.tabs(["Request (Mode A)", "Weekly plan (Mode B)", "Knowledge"])

with request_tab:
    text = st.text_area("What should the post be about?", placeholder="Reddit-style post about IFTA automation for 5-15 truck fleets")
    notes = st.text_input("Notes (optional)")
    if st.button("Run", type="primary"):
        try:
            request = Request(text=text, notes=notes or None)
        except ValidationError as e:
            st.error(e.errors()[0]["msg"])
        else:
            st.session_state.request_result = run_with_status("Drafting", lambda on_event: run_request(request, on_event=on_event))
    # session_state: any click reruns the whole script, and results would vanish from the other tab
    if st.session_state.get("request_result"):
        show_result(st.session_state.request_result)

with week_tab:
    day = st.date_input("Week of", value=datetime.date(2026, 10, 31))
    plan_clicked = st.button("Plan")
    draft_clicked = st.button("Draft all", type="primary")
    if plan_clicked or draft_clicked:
        st.session_state.week_day = day
    if st.session_state.get("week_day") == day:
        skipped: list[str] = []
        plan = plan_week(day, skipped=skipped)
        for n, item in enumerate(plan, 1):
            b = item.brief
            st.markdown(f"**{n}. {b.origin_ref}** ({b.origin}, {b.format}): {b.pain}  \n→ {b.hemut_feature}  \n_Why:_ {item.reason}")
        if skipped:
            st.markdown("**Left out:**\n" + "\n".join(f"- {line}" for line in skipped))
        if draft_clicked:
            st.session_state.week_results = []

            def draft_week(on_event):
                for result in run_week(day, plan, on_event=on_event):  # each result shows as soon as it is ready
                    st.session_state.week_results.append(result)
                    st.subheader(result.brief.origin_ref)
                    show_result(result)
            run_with_status("Drafting the week", draft_week)
        else:
            for result in st.session_state.get("week_results", []):
                st.subheader(result.brief.origin_ref)
                show_result(result)

with knowledge_tab:
    st.subheader("Seasons")
    st.dataframe([{"id": s.id, "window": f"{s.start} to {s.end}", "lead days": s.lead_days,
                   "verified": s.verified_by or "UNVERIFIED", "source": s.source_url} for s in load_seasons()])
    st.subheader("Claims")
    st.dataframe([{"id": c.id, "type": c.type, "approval": "needs approval" if c.requires_approval else "",
                   "wording": " | ".join(c.phrasings) or "(record only)", "checked": c.checked, "source": c.source_url}
                  for c in load_claims().values()])
