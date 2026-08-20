"""Streamlit shell for the slide study agent."""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

from study_agent import interface, paths, pipeline


def main() -> None:
    layout = paths.Layout()
    st.set_page_config(page_title="ENGR 689 Slide Study Agent", layout="wide")
    st.title("Slide Study Agent")

    subjects = interface.subject_options(layout)
    labels = [item.display_name for item in subjects]
    selected_label = st.selectbox("Subject", labels, index=0 if labels else None, placeholder="Create a subject first")
    selected = next((item for item in subjects if item.display_name == selected_label), None)

    with st.expander("Create subject"):
        new_subject = st.text_input("New subject name")
        if st.button("Create subject", disabled=not new_subject.strip()):
            selected = interface.create_subject(layout, new_subject)
            st.rerun()

    uploaded = st.file_uploader("PDF deck", type=["pdf"])
    if st.button("Start run", disabled=selected is None or uploaded is None):
        assert selected is not None and uploaded is not None
        temp_dir = Path(tempfile.mkdtemp())
        deck_path = temp_dir / uploaded.name
        deck_path.write_bytes(uploaded.getbuffer())
        deck_sha = paths.sha256_file(deck_path)
        deck_slug = paths.deck_slug(deck_path.name, deck_sha, layout.deck_slugs_with_hashes(selected.slug))
        started_at = datetime.now(timezone.utc)
        run_stamp = paths.utc_timestamp(started_at)
        run_dir = layout.run_dir(selected.slug, deck_slug, run_stamp)
        interface.write_active_run(layout, run_dir)
        _run_with_live_boxes(deck_path, selected.slug, layout, started_at)
        interface.clear_active_run(layout)
        st.rerun()

    if selected is None:
        st.info("Create or choose a subject to begin.")
        return

    summary = interface.latest_run_summary(layout, selected.slug)
    active_run = interface.read_active_run(layout)
    if active_run is not None:
        _render_stage_boxes(active_run)
    elif summary is None:
        st.info("No run artifacts yet.")
        _render_pending_stage_boxes()
        return
    else:
        _render_stage_boxes(summary.run_dir)

    if summary is not None:
        _render_summary(summary)
        _render_degraded(summary.run_dir)


def _run_with_live_boxes(
    deck_path: Path,
    subject_slug: str,
    layout: paths.Layout,
    started_at: datetime,
) -> None:
    boxes = {}
    for key, name in interface.STAGES:
        is_active = key in {"render", "page_reader"}
        boxes[key] = st.status(name, state="running" if is_active else "complete", expanded=is_active)
        with boxes[key]:
            st.write(f"{name} {'running.' if is_active else 'waiting for artifacts.'}")

    def log(line: str) -> None:
        with boxes["render"]:
            st.write(line)

    pipeline.run_render_pipeline(
        deck_path,
        subject_slug,
        layout=layout,
        started_at=started_at,
        read_pages=True,
        log=log,
    )
    for key, name in interface.STAGES:
        with boxes[key]:
            st.write(f"{name} summary will reload from disk.")
        boxes[key].update(state="complete", expanded=False)


def _render_pending_stage_boxes() -> None:
    for _, name in interface.STAGES:
        with st.status(f"{name} pending", state="complete", expanded=False):
            st.write(f"{name} waiting for artifacts.")


def _render_stage_boxes(run_dir: Path) -> None:
    for state in interface.stage_states(run_dir):
        label = state.name if state.state == "complete" else f"{state.name} {state.state}"
        with st.status(label, state="complete", expanded=state.state != "complete"):
            st.write(state.summary)
            for line in state.log_lines:
                st.write(line)


def _render_summary(summary: interface.RunSummary) -> None:
    st.header("Run summary")
    columns = st.columns(4)
    columns[0].metric("Slides read", summary.slides_read)
    columns[1].metric("Topics matched", summary.topics_matched)
    columns[2].metric("Topics new", summary.topics_new)
    columns[3].metric("Cost", f"${summary.total_cost_usd:.2f}")
    columns = st.columns(4)
    columns[0].metric("Lookups", summary.research_lookups)
    columns[1].metric("Cache hits", summary.research_cache_hits)
    columns[2].metric("Superseded frames", summary.superseded_count)
    columns[3].metric("Text-native pages", f"{summary.text_native_pages}/{summary.page_count}")
    st.write(f"Image-only deck: {'yes' if summary.image_only else 'no'}")


def _render_degraded(run_dir: Path) -> None:
    st.header("Failures and degraded reads")
    degraded = interface.degraded_reads(run_dir)
    if not degraded:
        st.write("No degraded reads.")
        return
    for item in degraded:
        left, right = st.columns([1, 2])
        if item.image_path.is_file():
            left.image(str(item.image_path), caption=f"Slide {item.slide_number}")
        else:
            left.write(f"Slide {item.slide_number} image missing.")
        right.subheader(f"{item.path_kind} slide {item.slide_number}")
        right.write(item.reader_note)
        right.json(item.note.model_dump(mode="json"))


if __name__ == "__main__":
    main()
