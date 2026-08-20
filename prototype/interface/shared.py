"""PROTOTYPE helpers shared by all three variants.

Deliberately limited to data access and the switcher bar. No shared layout: each
variant is free to throw the whole page structure away, which is the point of
having three of them.
"""

import io
import os

import streamlit as st

import fake_data as fd

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
VARIANTS = {
    "A": "Pipeline console",
    "B": "Slide workbench",
    "C": "Split ablation",
}


@st.cache_data(show_spinner=False)
def slide_png(slide_number, dpi=150):
    """Render one page of the committed Day 3 deck. Real render, fake everything else."""
    import pymupdf

    path = os.path.join(REPO_ROOT, fd.DECK_PATH)
    doc = pymupdf.open(path)
    page = doc[slide_number - 1]
    pix = page.get_pixmap(dpi=dpi)
    buf = io.BytesIO(pix.tobytes("png"))
    doc.close()
    return buf.getvalue()


def current_variant():
    v = st.query_params.get("variant", "A")
    return v if v in VARIANTS else "A"


def switcher_bar():
    """Fixed bar at the bottom of the page. Obviously not part of the design."""
    keys = list(VARIANTS)
    cur = current_variant()
    i = keys.index(cur)
    prev_key = keys[(i - 1) % len(keys)]
    next_key = keys[(i + 1) % len(keys)]
    st.markdown(
        f"""
        <style>
          .proto-bar {{
            position: fixed; bottom: 14px; left: 50%; transform: translateX(-50%);
            z-index: 1000; background: #111; color: #fff; border-radius: 999px;
            padding: 8px 14px; font: 600 13px/1 ui-sans-serif, system-ui;
            box-shadow: 0 6px 24px rgba(0,0,0,.35); display: flex; gap: 14px;
            align-items: center; border: 1px solid #444;
          }}
          .proto-bar a {{ color: #fff; text-decoration: none; font-size: 16px; }}
          .proto-bar span.tag {{ color: #ff9; letter-spacing: .04em; }}
        </style>
        <div class="proto-bar">
          <a href="?variant={prev_key}" target="_self">&#8592;</a>
          <span class="tag">PROTOTYPE</span>
          <span>{cur} &mdash; {VARIANTS[cur]}</span>
          <a href="?variant={next_key}" target="_self">&#8594;</a>
        </div>
        <div style="height:70px"></div>
        """,
        unsafe_allow_html=True,
    )


def init_state():
    ss = st.session_state
    ss.setdefault("subject", fd.SUBJECTS[0])
    ss.setdefault("uploaded", False)
    ss.setdefault("ran", False)
    ss.setdefault("selected_slide", 61)
    ss.setdefault("answers", {})
    ss.setdefault("graded", False)
    ss.setdefault("attempts", 0)
    ss.setdefault("speed", 0.02)


def grade():
    """Deterministic index comparison, no model call. Returns rows plus a topic rollup."""
    ss = st.session_state
    rows, rollup = [], {}
    for q in fd.QUIZ:
        chosen = ss.answers.get(q["question_id"])
        correct = chosen == q["correct_index"]
        rows.append({"q": q, "chosen": chosen, "correct": correct})
        seen, right = rollup.get(q["topic"], (0, 0))
        rollup[q["topic"]] = (seen + 1, right + (1 if correct else 0))
    return rows, rollup


def reset_run():
    for k in ("ran", "answers", "graded"):
        st.session_state.pop(k, None)
    init_state()
