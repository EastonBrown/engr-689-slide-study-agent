"""Variant C: Split ablation.

Structure: the screen is cut down the middle for the whole run. Left column is
the image path, right column is the text path, and they move in lockstep,
progress bar beside progress bar, note beside note, review beside review. A
scoreboard across the top counts figure-only facts recovered. The slide image
sits in the gutter between the two columns so both readings point at the same
page.

Primary affordance: comparison. The premise of the whole project is that slides
are a visual medium, and this variant makes the screen argue that continuously
rather than saving it for one eval table.
"""

import time

import streamlit as st

import fake_data as fd
from shared import grade, slide_png

# Hand-scored recovery for the four labeled facts. Case 4 is the weak one.
RECOVERY = {
    61: ("recovered", "not recovered"),
    28: ("recovered", "not recovered"),
    55: ("recovered", "not recovered"),
    10: ("partial", "partial"),
}


def render():
    ss = st.session_state
    st.markdown("### Image path versus text path")
    st.caption("Variant C, split ablation. Same deck, same prompt, same model, one difference.")

    bar = st.columns([2, 2, 1])
    with bar[0]:
        ss.subject = st.selectbox("Subject", fd.SUBJECTS, index=fd.SUBJECTS.index(ss.subject))
    with bar[1]:
        st.file_uploader("Deck (PDF)", type="pdf", key="upload_c")
    with bar[2]:
        st.write("")
        st.write("")
        if st.button("Run both paths", type="primary", width="stretch"):
            _animate()
            ss.ran = True

    if not ss.ran:
        st.info("Press Run both paths. The two columns fill at the same time.")
        return

    _scoreboard()
    st.divider()
    _slide_compare()
    st.divider()
    _review_compare()
    st.divider()
    _quiz()


def _animate():
    head = st.columns(2)
    head[0].markdown("**Image path**")
    head[1].markdown("**Text path**")
    lbar, rbar = head[0].progress(0.0), head[1].progress(0.0)
    llog, rlog = head[0].empty(), head[1].empty()
    centre = st.empty()
    ll, rl = [], []
    for n in range(1, fd.SLIDE_COUNT + 1):
        img = fd.slide_note(n, "image")
        txt = fd.slide_note(n, "text")
        ll.append(f"{n:>2}: {len(img['visuals'])} visual, {len(img['concepts'])} concept")
        rl.append(
            f"{n:>2}: EMPTY" if txt["reader_note"]
            else f"{n:>2}: 0 visual, {len(txt['concepts'])} concept"
        )
        lbar.progress(n / fd.SLIDE_COUNT, text=f"slide {n}")
        rbar.progress(n / fd.SLIDE_COUNT, text=f"slide {n}")
        llog.code("\n".join(ll[-6:]), language=None)
        rlog.code("\n".join(rl[-6:]), language=None)
        if n in fd.FIGURE_ONLY:
            with centre.container():
                st.image(slide_png(n), width=380)
                st.caption(f"slide {n}: hand-labeled figure-only fact")
            time.sleep(st.session_state.speed * 20)
        time.sleep(st.session_state.speed)
    centre.empty()


def _scoreboard():
    img_ok = sum(1 for v in RECOVERY.values() if v[0] == "recovered")
    txt_ok = sum(1 for v in RECOVERY.values() if v[1] == "recovered")
    cols = st.columns(4)
    cols[0].metric("Figure-only facts recovered, image", f"{img_ok} / 4", "1 partial")
    cols[1].metric("Figure-only facts recovered, text", f"{txt_ok} / 4", "1 partial")
    cols[2].metric("Visuals extracted", "112 / 0")
    cols[3].metric("Slides read", "66 / 65", "text path lost slide 56")
    st.caption(
        "Slide 10 is the weak case and is reported as partial on both sides rather "
        "than counted with the other three."
    )


def _slide_compare():
    ss = st.session_state
    st.markdown("#### Slide by slide")
    ss.selected_slide = st.select_slider(
        "slide", options=list(range(1, fd.SLIDE_COUNT + 1)), value=ss.selected_slide
    )
    n = ss.selected_slide
    left, mid, right = st.columns([2, 2, 2])
    with mid:
        st.image(slide_png(n), width="stretch")
        st.caption(f"slide {n}")
        if n in fd.FIGURE_ONLY:
            st.warning(fd.FIGURE_ONLY[n])
            st.write(f"image: **{RECOVERY[n][0]}**")
            st.write(f"text: **{RECOVERY[n][1]}**")
    with left:
        st.markdown("**Image path**")
        _short(fd.slide_note(n, "image"))
    with right:
        st.markdown("**Text path**")
        _short(fd.slide_note(n, "text"))


def _short(note):
    if note["reader_note"]:
        st.error(note["reader_note"])
    st.write(note["reading"] or "(empty)")
    st.caption(f"{len(note['visuals'])} visual(s), {len(note['concepts'])} concept(s)")
    for v in note["visuals"]:
        if v["assertion"]:
            st.info(f"`{v['kind']}` asserts: {v['assertion']}")


def _review_compare():
    st.markdown("#### The two reviews")
    left, right = st.columns(2)
    left.markdown("**From the image path**")
    left.markdown(fd.REVIEW_MD)
    right.markdown("**From the text path**")
    right.markdown(fd.TEXT_REVIEW_MD)


def _quiz():
    ss = st.session_state
    st.markdown("#### Knowledge check")
    visual = sum(1 for q in fd.QUIZ if q["source"] == "visual")
    st.caption(
        f"{visual} of 10 questions are marked `source: visual`. The text path "
        f"generates no quiz at all, so those {visual} are questions it could not have asked."
    )
    for i, q in enumerate(fd.QUIZ, start=1):
        tag = "VISUAL" if q["source"] == "visual" else "prose"
        st.markdown(f"**{i}. [{tag}] {q['stem']}**")
        choice = st.radio("options", q["options"], index=None,
                          key=f"c_{q['question_id']}", label_visibility="collapsed")
        if choice is not None:
            ss.answers[q["question_id"]] = q["options"].index(choice)
    if st.button("Submit", type="primary", key="submit_c"):
        ss.graded = True
        ss.attempts += 1
    if ss.graded:
        rows, rollup = grade()
        vis = [r for r in rows if r["q"]["source"] == "visual"]
        st.success(f"{sum(1 for r in rows if r['correct'])} of 10")
        st.write(
            f"On the {len(vis)} visual-sourced questions: "
            f"{sum(1 for r in vis if r['correct'])} correct."
        )
        for topic, (seen, right) in rollup.items():
            st.write(f"{topic}: {right} / {seen}" + ("" if seen >= 3 else "  (insufficient evidence)"))
