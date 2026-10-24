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

FORMAT = {"reddit_post": "Reddit post", "social_post": "Social post", "short_ad": "Short ad", "stat_card": "Stat card"}


def md(text: str) -> str:
    return text.replace("$", "\\$")  # two $ in markdown render as LaTeX


def on_event_for(status):
    """The thought process, kept short: the brief, the angles, then one line per finished draft."""
    def on_event(name: str, payload: dict) -> None:
        if name == "brief":
            status.markdown(md(f"**Brief** · {FORMAT[payload['format']]} for {payload['audience']}  \n"
                               f"Problem: {payload['pain']}  \nHemut answer: {payload['hemut_feature']}"))
        elif name == "angles":
            status.markdown(md("**Angles**\n" + "\n".join(f"{i}. {a['hook']}" for i, a in enumerate(payload["angles"], 1))))
        elif name == "draft" and not payload["violations"]:  # failed attempts are retried quietly
            status.markdown(f"Draft {payload['angle'] + 1} ready")
        elif name == "done":
            status.caption(f"Saved for review in {payload['run_dir']}")
    return on_event


def show_ad(text: str, needs_approval: bool) -> None:
    """One finished ad: title, body, CTA link. render_post joins those parts with blank lines."""
    parts = text.split("\n\n")
    with st.container(border=True):
        if needs_approval:
            st.badge("Approval needed", color="orange")
        st.markdown(md(f"#### {parts[0]}"))
        if len(parts) > 1:
            st.markdown(md("\n\n".join(parts[1:-1])))
            cta_text, _, url = parts[-1].rpartition(" ")
            st.markdown(md(f"**[{cta_text} →]({url})**"))


def show_result(result: RunResult) -> None:
    if result.needs_source:
        st.warning(md("**Needs a source before anything is drafted.** Nothing in the knowledge base covers:\n\n"
                      + "\n".join(f"- {item}" for item in result.needs_source)))
    elif result.status == "blocked_sensitive":
        st.error("**Blocked: sensitive topic.** A human decides whether to write about this.")
    passed = [a[-1] for a in result.drafts if a and not a[-1].violations and a[-1].rendered_text]
    for last in passed:  # drafts that never passed the checks are not shown
        show_ad(last.rendered_text, bool(last.raw_post and last.raw_post.requires_approval))
    if result.drafts and not passed:
        st.info("No draft passed the review checks this time. Run it again.")


def run_with_status(label: str, job):
    """Run job(on_event) inside a status box; show a plain error (details folded away) instead of a traceback."""
    status = st.status(label, expanded=True)
    try:
        out = job(on_event_for(status))
    except Exception as e:
        status.update(label=f"{label}: failed", state="error")
        st.error("**Status: error.** Drafting stopped before it finished. Anything done so far was saved for review.")
        with st.expander("Details"):
            st.text(f"{type(e).__name__}: {e}\n" + "\n".join(getattr(e, "__notes__", [])))
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
        if st.session_state.get("week_day") != day:  # drafts belong to one week's plan
            st.session_state.week_results = []
        st.session_state.week_day = day
    if st.session_state.get("week_day") == day:
        skipped: list[str] = []
        plan = plan_week(day, skipped=skipped)
        for n, item in enumerate(plan, 1):
            b = item.brief
            st.markdown(md(f"**{n}. {b.pain}**  \n{b.origin.capitalize()} · {FORMAT[b.format]} · Hemut answer: {b.hemut_feature}  \n"
                           f"_Why:_ {item.reason}"))
        if skipped:
            st.markdown("**Left out:**\n" + "\n".join(f"- {line}" for line in skipped))
        if draft_clicked:
            st.session_state.week_results = []

            def draft_week(on_event):
                for result in run_week(day, plan, on_event=on_event):  # each result shows as soon as it is ready
                    st.session_state.week_results.append(result)
                    st.subheader(md(result.brief.pain))
                    show_result(result)
            run_with_status("Drafting the week", draft_week)
        else:
            for result in st.session_state.get("week_results", []):
                st.subheader(md(result.brief.pain))
                show_result(result)

with knowledge_tab:
    st.subheader("Seasons")
    st.dataframe([{"id": s.id, "window": f"{s.start} to {s.end}", "lead days": s.lead_days,
                   "verified": s.verified_by or "UNVERIFIED", "source": s.source_url} for s in load_seasons()])
    st.subheader("Claims")
    st.dataframe([{"id": c.id, "type": c.type, "approval": "needs approval" if c.requires_approval else "",
                   "wording": " | ".join(c.phrasings) or "(record only)", "checked": c.checked, "source": c.source_url}
                  for c in load_claims().values()])
