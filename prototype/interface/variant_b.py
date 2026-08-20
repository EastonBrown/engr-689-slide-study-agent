"""Variant B: Slide workbench.

Structure: the deck itself is the interface. A 66-row filmstrip runs down the
left and lights up row by row as the run proceeds. Clicking any row opens an
inspector on the right holding the page image at full width beside the SlideNote
it produced, with the text-path note for the same slide behind a tab. Review,
quiz, and memory are top-level tabs, not a scroll position.

Primary affordance: pick a slide, inspect it. Per-slide inspection is the centre
of gravity rather than a detail inside a log, and the image-versus-text ablation
is a tab on every single slide rather than a separate screen.
"""

import time

import streamlit as st

import fake_data as fd
from shared import grade, slide_png

_ICON = {"done": "*", "degraded": "!", "pending": "."}


def render():
    ss = st.session_state
    st.markdown("### Slide workbench")
    st.caption("Variant B, the deck is the interface. Left: every slide. Right: what came off it.")

    top = st.columns([2, 2, 1, 1])
    with top[0]:
        ss.subject = st.selectbox("Subject", fd.SUBJECTS, index=fd.SUBJECTS.index(ss.subject))
    with top[1]:
        st.file_uploader("Deck (PDF)", type="pdf", key="upload_b")
    with top[2]:
        st.write("")
        st.write("")
        if st.button("Run", type="primary", width="stretch"):
            _animate()
            ss.ran = True
    with top[3]:
        st.write("")
        st.write("")
        st.button("Stop", width="stretch", disabled=True)

    st.divider()
    tabs = st.tabs(["Slides", "Review", "Quiz", "Memory"])
    with tabs[0]:
        _slides()
    with tabs[1]:
        _review()
    with tabs[2]:
        _quiz()
    with tabs[3]:
        _memory()


def _animate():
    holder = st.empty()
    bar = st.progress(0.0)
    for n in range(1, fd.SLIDE_COUNT + 1):
        note = fd.slide_note(n, "image")
        with holder.container():
            a, b = st.columns([1, 2])
            a.image(slide_png(n), width="stretch")
            b.markdown(f"**Reading slide {n}**")
            b.write(note["reading"][:180])
            b.caption(
                f"{len(note['visuals'])} visual(s), {len(note['concepts'])} concept(s), "
                f"{len(note['verbatim_spans'])} verbatim span(s)"
            )
        bar.progress(n / fd.SLIDE_COUNT, text=f"slide {n} of {fd.SLIDE_COUNT}")
        time.sleep(st.session_state.speed)
    holder.empty()
    bar.empty()


def _slides():
    ss = st.session_state
    if not ss.ran:
        st.info("Press Run. The filmstrip fills in as each slide is read.")
        return

    left, right = st.columns([1, 3])

    with left:
        st.caption("66 slides, 65 clean, 1 degraded")
        show_only = st.checkbox("Only slides with a figure-only fact", value=False)
        listing = sorted(fd.FIGURE_ONLY) if show_only else range(1, fd.SLIDE_COUNT + 1)
        with st.container(height=560):
            for n in listing:
                note = fd.slide_note(n, "image")
                state = "degraded" if note["reader_note"] else "done"
                star = " [fig]" if n in fd.FIGURE_ONLY else ""
                label = f"{_ICON[state]} {n:>2}  {(note['title'] or 'untitled')[:22]}{star}"
                if st.button(label, key=f"row_{n}", width="stretch"):
                    ss.selected_slide = n

    with right:
        n = ss.selected_slide
        st.markdown(f"#### Slide {n}")
        img_col, note_col = st.columns([1, 1])
        with img_col:
            st.image(slide_png(n), width="stretch")
            st.caption("rendered at 150 DPI, exactly what the reader was given")
        with note_col:
            path_tabs = st.tabs(["Image path", "Text path", "Raw JSON"])
            with path_tabs[0]:
                _note_body(fd.slide_note(n, "image"))
            with path_tabs[1]:
                _note_body(fd.slide_note(n, "text"))
            with path_tabs[2]:
                st.json(fd.slide_note(n, "image"))
        if n in fd.FIGURE_ONLY:
            st.warning(f"Hand-labeled figure-only fact on this slide: {fd.FIGURE_ONLY[n]}")


def _note_body(note):
    if note["reader_note"]:
        st.error(f"reader_note: {note['reader_note']}")
    st.caption(f"page_role: {note['page_role']}")
    st.markdown("**Reading**")
    st.write(note["reading"] or "(empty)")
    st.markdown("**Visuals**")
    if not note["visuals"]:
        st.write("none")
    for v in note["visuals"]:
        st.write(f"`{v['kind']}` {v['description']}")
        if v["assertion"]:
            st.info(f"asserts: {v['assertion']}")
    st.markdown("**Concepts**")
    if not note["concepts"]:
        st.write("none")
    for c in note["concepts"]:
        st.write(f"{c['name']} ({c['status']}) - {c['why_it_matters']}")
    st.markdown("**Verbatim spans**")
    st.write(note["verbatim_spans"] or "none")


def _review():
    ss = st.session_state
    if not ss.ran:
        st.info("Run first.")
        return
    st.markdown(fd.REVIEW_MD)
    st.divider()
    st.caption("Every bracketed slide number opens that slide in the Slides tab.")
    cols = st.columns(6)
    for i, n in enumerate([10, 28, 48, 55, 56, 61]):
        if cols[i].button(f"slide {n}", key=f"jump_{n}", width="stretch"):
            ss.selected_slide = n


def _quiz():
    ss = st.session_state
    if not ss.ran:
        st.info("Run first.")
        return
    for i, q in enumerate(fd.QUIZ, start=1):
        with st.container(border=True):
            head, cite = st.columns([4, 1])
            head.markdown(f"**{i}. {q['stem']}**")
            cite.image(slide_png(q["slide_citations"][0]), width="stretch")
            cite.caption(f"slide {q['slide_citations'][0]}")
            choice = head.radio("options", q["options"], index=None,
                                key=f"b_{q['question_id']}", label_visibility="collapsed")
            if choice is not None:
                ss.answers[q["question_id"]] = q["options"].index(choice)
            head.caption(f"topic: {q['topic']} | source: {q['source']}")
    if st.button("Submit", type="primary", key="submit_b"):
        ss.graded = True
        ss.attempts += 1
    if ss.graded:
        rows, rollup = grade()
        st.success(f"{sum(1 for r in rows if r['correct'])} of 10")
        for i, r in enumerate(rows, start=1):
            q = r["q"]
            with st.expander(f"{i}. {'correct' if r['correct'] else 'wrong'}"):
                c1, c2 = st.columns([1, 2])
                c1.image(slide_png(q["slide_citations"][0]), width="stretch")
                c2.write(f"Answer: {q['options'][q['correct_index']]}")
                c2.write(q["explanation"])
                if r["chosen"] is not None and not r["correct"]:
                    c2.warning(q["distractor_rationale"][r["chosen"]])


def _memory():
    ss = st.session_state
    st.caption(f"Subject: {ss.subject}")
    rollup = grade()[1] if ss.graded else {}
    rows = []
    for t in fd.TOPICS:
        seen, right = rollup.get(t, (0, 0))
        rows.append({
            "topic": t,
            "exposure (slides)": {"Computer vision as a field": 14, "Vision encoders": 12,
                                  "Contrastive image-text pretraining": 11,
                                  "Vision language model architectures": 10,
                                  "Compositionality and generation": 9,
                                  "Agent definitions": 10}[t],
            "performance": f"{right} / {seen}" if seen >= 3 else "insufficient evidence",
            "decks": 1,
        })
    st.dataframe(rows, width="stretch", hide_index=True)
    st.caption("Exposure and performance are two axes and are never averaged together.")
    st.button("Generate a retake", disabled=ss.attempts == 0, key="retake_b",
              help="Refuses with no attempts on record.")
