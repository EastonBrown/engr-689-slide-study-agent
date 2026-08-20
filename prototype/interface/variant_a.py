"""Variant A: Pipeline console.

Structure: one long scrolling page. The run is a vertical stack of stage boxes
that open, fill with live detail, and collapse as they finish. Slide images
appear inline inside the page-read log, small, as evidence that a particular
slide was seen. The text baseline runs but is not shown; it is an eval number
reported at the end, not a screen.

Primary affordance: scroll. The demo is a single unbroken narrative from upload
to grade, which is the easiest thing to film in one take.
"""

import time

import streamlit as st

import fake_data as fd
from shared import slide_png


def render():
    st.title("Slide deck to study guide")
    st.caption("Variant A, pipeline console. One page, top to bottom.")

    ss = st.session_state

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        ss.subject = st.selectbox("Subject", fd.SUBJECTS, index=fd.SUBJECTS.index(ss.subject))
    with c2:
        st.file_uploader("Deck (PDF)", type="pdf", key="upload_a")
        st.caption(f"Prototype always runs `{fd.DECK_PATH}`.")
    with c3:
        st.write("")
        st.write("")
        go = st.button("Run pipeline", type="primary", width="stretch")

    if go:
        _animate()
        ss.ran = True

    if not ss.ran:
        st.info("Nothing has run yet. Press Run pipeline.")
        return

    _stage_summary()
    st.divider()
    _failures()
    st.divider()
    _review()
    st.divider()
    _comparison()
    st.divider()
    _quiz()


def _animate():
    ss = st.session_state
    delay = ss.speed

    with st.status("Render, 66 pages at 150 DPI", expanded=True) as s:
        bar = st.progress(0.0)
        for n in range(1, fd.SLIDE_COUNT + 1):
            bar.progress(n / fd.SLIDE_COUNT, text=f"page {n} of {fd.SLIDE_COUNT}")
            time.sleep(delay / 3)
        s.update(label="Render, 66 pages at 150 DPI, done", state="complete", expanded=False)

    with st.status("Page read, image path", expanded=True) as s:
        bar = st.progress(0.0)
        log = st.empty()
        img = st.empty()
        lines = []
        for n in range(1, fd.SLIDE_COUNT + 1):
            note = fd.slide_note(n, "image")
            flag = " DEGRADED" if note["reader_note"] else ""
            lines.append(
                f"slide {n:>2}: {len(note['visuals'])} visual(s), "
                f"{len(note['concepts'])} concept(s){flag}"
            )
            bar.progress(n / fd.SLIDE_COUNT, text=f"slide {n} of {fd.SLIDE_COUNT}")
            log.code("\n".join(lines[-8:]), language=None)
            if n in fd.HIGHLIGHTS:
                img.image(slide_png(n), caption=f"slide {n}", width=420)
            time.sleep(delay)
        s.update(label="Page read, image path, 66 of 66, 1 degraded",
                 state="complete", expanded=False)

    with st.status("Page read, text path (baseline)", expanded=False) as s:
        bar = st.progress(0.0)
        for n in range(1, fd.SLIDE_COUNT + 1):
            bar.progress(n / fd.SLIDE_COUNT, text=f"slide {n}")
            time.sleep(delay / 4)
        s.update(label="Page read, text path, 65 of 66, slide 56 empty",
                 state="complete", expanded=False)

    with st.status("Outline", expanded=True) as s:
        st.write("6 topics assigned. 0 matched an existing topic, 6 declared new.")
        for t in fd.TOPICS:
            st.write(f"new topic: {t}")
            time.sleep(delay * 3)
        s.update(label="Outline, 6 topics, 0 matched, 6 new", state="complete", expanded=False)

    with st.status("Research", expanded=True) as s:
        for name, slide, how in fd.RESEARCH_LOOKUPS:
            st.write(f"`named_only` {name} (slide {slide}) -> {how}")
            time.sleep(delay * 6)
        s.update(label="Research, 4 lookups, 2 cache hits", state="complete", expanded=False)

    with st.status("Review", expanded=False) as s:
        time.sleep(delay * 10)
        s.update(label="Review written, 4 sections, 6 slide citations",
                 state="complete", expanded=False)

    with st.status("Quiz", expanded=True) as s:
        for q in fd.QUIZ:
            st.write(f"{q['question_id']} [{q['source']}] slides {q['slide_citations']}")
            time.sleep(delay * 4)
        s.update(label="Quiz, 10 questions, 6 visual, 4 prose",
                 state="complete", expanded=False)


def _stage_summary():
    st.subheader("Run summary")
    a, b, c, d = st.columns(4)
    a.metric("Slides read", "66 / 66", "1 degraded")
    b.metric("Topics", "6", "6 new")
    c.metric("Research lookups", "4", "2 cache hits")
    d.metric("Cost", "$0.00", "prototype")
    st.caption(
        "Text baseline read 65 of 66. The image and text comparison is reported "
        "in the eval table, not shown as a screen in this variant."
    )


def _failures():
    """Every slide the reader could not read cleanly. Resume is a grep for this."""
    bad = [n for n in range(1, fd.SLIDE_COUNT + 1)
           if fd.slide_note(n, "image")["reader_note"]]
    st.subheader(f"Failures and degraded reads ({len(bad)})")
    if not bad:
        st.write("None. Every slide read cleanly.")
        return
    st.caption(
        "A failed slide still writes its file with `reader_note` set, so nothing "
        "is silently dropped and a re-run retries exactly these."
    )
    for n in bad:
        note = fd.slide_note(n, "image")
        img_col, txt_col = st.columns([1, 3])
        img_col.image(slide_png(n), width="stretch")
        txt_col.error(f"**slide {n}** - {note['reader_note']}")
        txt_col.caption("The page image is kept so the failure can be looked at, not guessed at.")


def _review():
    st.subheader("Lesson review")
    st.caption("Pick a cited slide to pull the page and the note it produced up beside the text.")
    left, right = st.columns([3, 2])
    with left:
        st.markdown(fd.REVIEW_MD)
    with right:
        cited = [10, 28, 48, 55, 56, 61]
        pick = st.radio("Cited slides", cited, horizontal=True, key="cite_a")
        st.image(slide_png(pick), caption=f"slide {pick}", width="stretch")
        _note_beside(fd.slide_note(pick, "image"))


def _note_beside(note):
    """The SlideNote for the cited slide, so the run's per-slide work outlives the log."""
    st.caption(f"page_role: {note['page_role']}")
    for v in note["visuals"]:
        st.write(f"**{v['kind']}** {v['description']}")
        if v["assertion"]:
            st.info(f"asserts: {v['assertion']}")
    if note["concepts"]:
        st.write("**Concepts**")
        for c in note["concepts"]:
            st.write(f"- {c['name']} (`{c['status']}`)")
    if note["verbatim_spans"]:
        st.caption("verbatim: " + " | ".join(note["verbatim_spans"]))


def _comparison():
    """The one place the text baseline gets a screen. Everything else about it is eval."""
    st.subheader("Image path against text path")
    st.caption(
        "Same deck, same prompt, same model, one difference. Slide 10 is the weak "
        "case of the four and is reported as partial on both sides rather than "
        "counted with the other three."
    )
    cols = st.columns(3)
    cols[0].metric("Figure-only facts recovered", "3 / 4", "text path: 0 / 4")
    cols[1].metric("Visuals extracted", "112", "text path: 0")
    cols[2].metric("Slides read", "66 / 66", "text path: 65, slide 56 empty")

    left, right = st.columns(2)
    left.markdown("**Review written from the image path**")
    left.markdown(fd.REVIEW_MD)
    right.markdown("**Review written from the text path**")
    right.markdown(fd.TEXT_REVIEW_MD)


def _quiz():
    ss = st.session_state
    st.subheader("Knowledge check")
    st.caption("Ten questions, four options, one correct. Format matches the instructors' Quiz 3.")

    for i, q in enumerate(fd.QUIZ, start=1):
        st.markdown(f"**{i}. {q['stem']}**")
        choice = st.radio(
            "options", q["options"], index=None, key=f"a_{q['question_id']}",
            label_visibility="collapsed",
        )
        if choice is not None:
            ss.answers[q["question_id"]] = q["options"].index(choice)
        st.caption(f"slides {q['slide_citations']} | topic: {q['topic']} | source: {q['source']}")
        st.write("")

    if st.button("Submit answers", type="primary"):
        ss.graded = True
        ss.attempts += 1

    if ss.graded:
        from shared import grade

        rows, rollup = grade()
        score = sum(1 for r in rows if r["correct"])
        st.success(f"{score} of 10")
        for i, r in enumerate(rows, start=1):
            q = r["q"]
            mark = "correct" if r["correct"] else "wrong"
            with st.expander(f"{i}. {mark}: {q['stem'][:70]}"):
                st.write(f"Answer: {q['options'][q['correct_index']]}")
                st.write(q["explanation"])
                if r["chosen"] is not None and not r["correct"]:
                    st.write(f"You picked: {q['distractor_rationale'][r['chosen']]}")
        st.subheader("Per topic")
        for topic, (seen, right) in rollup.items():
            st.write(f"{topic}: {right} / {seen}" + ("" if seen >= 3 else "  (insufficient evidence)"))
        st.button("Generate a retake", key="retake_a")
