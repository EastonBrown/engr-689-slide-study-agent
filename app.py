"""The one-page Streamlit interface (issue #25).

Run with ``streamlit run app.py``.  The script intentionally keeps no run
state: once a PDF has been accepted, the pipeline writes a run directory and
every later rerun reconstructs this screen from that directory.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from study_agent import memory, paths, pipeline, run_view
from study_agent.schemas import PathKind
from study_agent.stages import outline, page_reader


def _uploaded_pdf(uploaded: st.runtime.uploaded_file_manager.UploadedFile) -> Path:
    """Persist an upload just long enough to hand its bytes to the pipeline.

    It lives outside the run tree because the deck's hash, not its uploaded
    filename, identifies the run.  The directory is gitignored with ``out/``.
    """

    target = paths.Layout().root / "out" / "uploads" / uploaded.name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(uploaded.getvalue())
    return target


def _status_state(state: run_view.StageState) -> str:
    return {
        run_view.StageState.complete: "complete",
        run_view.StageState.failed: "error",
        run_view.StageState.running: "running",
        run_view.StageState.pending: "running",
    }[state]


def _render_stage_views(run_dir: Path | None) -> None:
    """Replay the seven boxes from disk, with pending stages left visibly open."""

    views = run_view.stage_views(run_dir or Path(".not-a-run"))
    for view in views:
        expanded = view.state in {run_view.StageState.running, run_view.StageState.pending}
        label = f"{view.label}: {view.summary}"
        with st.status(label, expanded=expanded, state=_status_state(view.state)):
            if view.detail:
                st.code("\n".join(view.detail), language=None)
            elif view.state is run_view.StageState.pending:
                st.caption("Pending — this stage has not written artifacts yet.")


def _render_summary(run_dir: Path) -> None:
    summary = run_view.run_summary(run_dir)
    if summary is None:
        return
    st.subheader("Run summary")
    slides = f"{summary.slides_read} / {summary.slides_total}"
    if summary.degraded:
        slides += f" ({summary.degraded} degraded)"
    topics = "pending"
    if summary.outline_ran:
        topics = f"{summary.topics_matched} matched · {summary.topics_new} new"
    columns = st.columns(4)
    columns[0].metric("Slides read", slides)
    columns[1].metric("Topics", topics)
    columns[2].metric("Research", f"{summary.research_lookups} lookups · {summary.research_cache_hits} hits")
    columns[3].metric("Cost", f"${summary.cost_usd:.4f}")
    st.caption(f"{summary.deck_filename} · {summary.model} · prompt {summary.prompt_version}")

    st.markdown("**Preflight**")
    st.write(
        f"{summary.page_count} pages; {summary.superseded_count} superseded build-up frame(s); "
        f"{'image-only deck' if summary.image_only else 'text baseline available'}; "
        f"{'downscaled' if summary.downscaled else 'native render resolution'}."
    )
    if summary.superseded:
        st.caption(f"Superseded frames: {', '.join(str(slide) for slide in summary.superseded)}")


def _render_failures(run_dir: Path) -> None:
    found = run_view.failures(run_dir)
    if not found:
        return
    st.subheader("Failures and degraded reads")
    for item in found:
        text, image = st.columns([3, 2])
        with text:
            st.warning(f"Slide {item.slide_number} · {item.path} path")
            st.write(item.reader_note)
        with image:
            if item.image_path is None:
                st.caption("The rendered page image is unavailable.")
            else:
                st.image(str(item.image_path), caption=f"Slide {item.slide_number}")


def _run(uploaded: st.runtime.uploaded_file_manager.UploadedFile, subject_slug: str) -> Path:
    """Run the available pipeline stages while their Streamlit boxes are open."""

    deck_path = _uploaded_pdf(uploaded)
    layout = paths.Layout()
    with st.status("Render and preflight", expanded=True) as status:
        lines: list[str] = []
        log = st.empty()

        def render_log(message: str) -> None:
            lines.append(message)
            log.code("\n".join(lines), language=None)

        result = pipeline.run_render_pipeline(
            deck_path, subject_slug, layout=layout, log=render_log
        )
        status.update(label="Render and preflight: complete", state="complete", expanded=False)

    run_dir = result.run_dir
    placeholders: dict[PathKind, st.delta_generator.DeltaGenerator] = {}
    statuses: dict[PathKind, st.delta_generator.DeltaGenerator] = {}
    for path_kind, label in (
        (PathKind.image, "Page read, image path"),
        (PathKind.text, "Page read, text path (baseline)"),
    ):
        status = st.status(label, expanded=True)
        statuses[path_kind] = status
        placeholders[path_kind] = st.empty()

    lines_by_path: dict[PathKind, list[str]] = {
        PathKind.image: [], PathKind.text: []
    }

    def reader_log(path_kind: PathKind, message: str) -> None:
        lines_by_path[path_kind].append(message)
        placeholders[path_kind].code("\n".join(lines_by_path[path_kind][-20:]), language=None)

    page_reader.read_run_pages(run_dir, log=reader_log)
    for path_kind, label in (
        (PathKind.image, "Page read, image path"),
        (PathKind.text, "Page read, text path (baseline)"),
    ):
        statuses[path_kind].update(label=f"{label}: complete", state="complete", expanded=False)

    with st.status("Outline", expanded=True) as status:
        outline.outline_run(
            run_dir,
            deck_slug=result.manifest.deck_slug,
            superseded=result.manifest.preflight.superseded,
            subject_slug=subject_slug,
            layout=layout,
        )
        status.update(label="Outline: complete", state="complete", expanded=False)
    for label in ("Research", "Review", "Quiz"):
        with st.status(f"{label}: not run", expanded=True):
            st.caption("Pending — this stage has not written artifacts yet.")
    return run_dir


def main() -> None:
    st.set_page_config(page_title="Slide deck to study guide", layout="wide")
    st.title("Slide deck to study guide")
    st.caption("Image-path study guide with a text-path baseline")

    layout = paths.Layout()
    subjects = memory.list_subjects(layout)
    names = [subject.display_name for subject in subjects]
    lookup = {subject.display_name: subject.slug for subject in subjects}

    controls = st.columns([2, 2, 1])
    with controls[0]:
        selected_name = st.selectbox("Subject", names, index=None, placeholder="Choose a subject")
    with controls[1]:
        uploaded = st.file_uploader("Deck (PDF)", type="pdf")
    with controls[2]:
        st.write("")
        run = st.button("Run pipeline", type="primary", disabled=not (selected_name and uploaded))

    with st.expander("Create a subject"):
        display_name = st.text_input("New subject name")
        if st.button("Create subject"):
            try:
                created = memory.create_subject(display_name, layout)
            except (ValueError, memory.SubjectExists) as error:
                st.error(str(error))
            else:
                st.success(f"Created {created.display_name}. Choose it above.")

    selected_slug = lookup.get(selected_name or "")
    run_dir = run_view.latest_run(layout, selected_slug) if selected_slug else None
    ran_this_request = bool(run and uploaded and selected_slug)
    if ran_this_request:
        try:
            run_dir = _run(uploaded, selected_slug)
        except (pipeline.PipelineError, page_reader.PageReadFailed) as error:
            st.error(str(error))
        except Exception as error:  # Streamlit should preserve and surface any artifacts already written.
            st.exception(error)

    if not ran_this_request:
        _render_stage_views(run_dir)
    if run_dir is not None:
        _render_summary(run_dir)
        _render_failures(run_dir)


if __name__ == "__main__":
    main()
