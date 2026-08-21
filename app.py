"""The one-page Streamlit interface (issue #25).

Run with ``streamlit run app.py``.  The script intentionally keeps no run
state: once a PDF has been accepted, the pipeline writes a run directory and
every later rerun reconstructs this screen from that directory.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
from typing import Any

import streamlit as st

from study_agent import memory, paths, pipeline, replay, run_view
from study_agent.schemas import PathKind, Quiz, SlideNote
from study_agent.stages import grade, outline, page_reader, retake


_CITATION = re.compile(r"\[(?:slide|slides)\s+([0-9]+(?:\s*,\s*[0-9]+)*)\]", re.I)


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


def _notes(run_dir: Path, path_kind: PathKind) -> dict[int, SlideNote]:
    notes: dict[int, SlideNote] = {}
    for target in sorted(paths.notes_dir(run_dir, path_kind.value).glob("*.json")):
        payload = paths.read_json(target)
        if payload is not None:
            try:
                note = SlideNote.model_validate(payload)
            except Exception:
                continue
            notes[note.slide_number] = note
    return notes


def _review(run_dir: Path, path_kind: PathKind) -> str | None:
    target = paths.review_file(run_dir, path_kind.value)
    return paths.read_text(target) if target.is_file() else None


def _cited_slides(markdown: str) -> list[int]:
    return sorted({int(number) for match in _CITATION.findall(markdown) for number in match.split(",")})


def _render_review(run_dir: Path, path_kind: PathKind, *, title: str) -> None:
    markdown = _review(run_dir, path_kind)
    if markdown is None:
        st.info(f"{title} is not available yet.")
        return
    st.markdown(markdown)
    cited = _cited_slides(markdown)
    if not cited:
        return
    selected = st.selectbox(
        f"Show cited slide ({path_kind.value} path)", cited,
        key=f"citation-{path_kind.value}",
    )
    image = paths.page_render_png(run_dir, selected)
    notes = _notes(run_dir, path_kind)
    left, right = st.columns([2, 3])
    with left:
        if image.is_file():
            st.image(str(image), caption=f"Slide {selected}")
        else:
            st.caption(f"Slide image {selected} is unavailable.")
    with right:
        note = notes.get(selected)
        if note is None:
            st.caption("The SlideNote for this citation is unavailable.")
        else:
            st.json(note.model_dump())


def _fact_score(path_kind: PathKind, deck_slug: str) -> tuple[int, int] | None:
    """Figure-only fact recovery for one path, or None when it is not scored.

    ADR 0006 makes this a hand judgement: a hit is the fact appearing anywhere
    in that slide's `SlideNote`, in any field, which is not a string match. An
    earlier version of this function tried to decide it by searching for the
    label's English sentence inside the note, which can never match and so
    reported every path as zero. A zero the reader takes for a measurement is
    worse than an absence, so a fact that has not been scored by hand is
    reported as unscored instead.

    Scores are read from the label file: a fact carries `scored`, mapping a
    path name to whether that path recovered it. The score is shown only when
    every labelled fact carries one for this path, so a partial hand pass is
    never presented as a total.
    """

    payload = paths.read_json(paths.Layout().figure_only_facts_file())
    if not isinstance(payload, dict) or payload.get("deck_slug") != deck_slug:
        return None
    facts = payload.get("facts", [])
    if not facts:
        return None
    hits = 0
    for fact in facts:
        scored = fact.get("scored")
        if not isinstance(scored, dict) or path_kind.value not in scored:
            return None
        hits += bool(scored[path_kind.value])
    return hits, len(facts)


def _render_comparison(run_dir: Path) -> None:
    summary = run_view.run_summary(run_dir)
    if summary is None:
        return
    st.subheader("Image path against text path")
    image_notes = _notes(run_dir, PathKind.image)
    text_notes = _notes(run_dir, PathKind.text)
    image_visuals = sum(len(note.visuals) for note in image_notes.values())
    text_visuals = sum(len(note.visuals) for note in text_notes.values())
    image_score = _fact_score(PathKind.image, summary.deck_slug)
    text_score = _fact_score(PathKind.text, summary.deck_slug)
    columns = st.columns(3)
    columns[0].metric("Slides read", f"{summary.slides_read} / {summary.slides_total}", f"baseline {summary.text_slides_read} / {summary.text_slides_total}")
    columns[1].metric("Visuals found", f"{image_visuals}", f"baseline {text_visuals}")
    if image_score is not None and text_score is not None:
        columns[2].metric(
            "Figure-only recovery",
            f"{image_score[0]} / {image_score[1]}",
            f"baseline {text_score[0]} / {text_score[1]}",
        )
    else:
        columns[2].metric("Figure-only recovery", "scored by hand")
        columns[2].caption("See eval/results.md. ADR 0006 makes this a judgement, not a string match.")
    if summary.image_only:
        st.info("Text path not applicable, this deck is image-only.")
    st.caption("Slide 10 is partial on both sides: its labels extract, but the spatial relation does not.")
    image_review, text_review = st.columns(2)
    with image_review:
        _render_review(run_dir, PathKind.image, title="Image-path review")
    with text_review:
        _render_review(run_dir, PathKind.text, title="Text-path review")


def _load_quiz(target: Path) -> Quiz | None:
    payload = paths.read_json(target)
    if payload is None:
        return None
    try:
        return Quiz.model_validate(payload)
    except Exception:
        return None


def _render_quiz(run_dir: Path, subject_slug: str, layout: paths.Layout) -> None:
    quiz = _load_quiz(paths.quiz_file(run_dir))
    if quiz is None:
        return
    st.subheader("Quiz")
    st.caption(f"{len(quiz.questions)} questions drawn from {quiz.covered_slide_count} covered slides.")
    answers: list[int | None] = []
    for number, question in enumerate(quiz.questions):
        answer = st.radio(question.stem, question.options, index=None, key=f"answer-{quiz.quiz_id}-{number}")
        answers.append(question.options.index(answer) if answer is not None else None)
    result_payload: Any = None
    if st.button("Submit quiz", key=f"submit-{quiz.quiz_id}"):
        try:
            result = grade.grade_run(run_dir, answers, layout=layout)
        except (grade.GradeError, memory.UnknownSubject) as error:
            st.error(str(error))
        else:
            result_payload = result.model_dump()
    if result_payload is None:
        quiz_hash = paths.sha256_file(paths.quiz_file(run_dir))
        for attempt in reversed(memory.read_attempts(subject_slug, layout).attempts):
            if attempt.quiz_sha256 == quiz_hash:
                chosen = [response.chosen_index if response.chosen_index >= 0 else None for response in attempt.responses]
                result_payload = grade.grade_quiz(quiz, chosen, quiz_sha256=quiz_hash).model_dump()
                break
    if isinstance(result_payload, dict):
        _render_grade(result_payload)
    attempts = memory.read_attempts(subject_slug, layout).attempts
    if attempts and st.button("Generate retake", key=f"retake-{subject_slug}"):
        try:
            retake.retake_run(subject_slug, layout=layout)
        except retake.RetakeError as error:
            st.warning(str(error))
        else:
            st.success("Retake written. Rerun the page to open it.")
    elif not attempts:
        st.caption("Retake unavailable until a quiz has been graded.")


def _render_grade(payload: dict[str, Any]) -> None:
    st.subheader("Grade")
    st.write(f"{payload.get('correct', 0)} / {payload.get('total', 0)}")
    for question in payload.get("questions", []):
        verdict = "Correct" if question.get("correct") else "Incorrect"
        st.markdown(f"**{verdict}:** {question.get('stem', '')}")
        st.write(question.get("explanation", ""))
        if question.get("chosen_rationale"):
            st.caption(f"Chosen option: {question['chosen_rationale']}")
    if payload.get("rollup"):
        st.table(payload["rollup"])


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
    # Memory is derived only from the image-path outline. The text path remains
    # a baseline and never contributes exposure or topic citations.
    with st.status("Research", expanded=True) as status:
        from study_agent.stages import research, review, quiz
        research.research_run(run_dir, layout=layout)
        status.update(label="Research: complete", state="complete", expanded=False)
    with st.status("Review", expanded=True) as status:
        review.review_run(run_dir)
        status.update(label="Review: complete", state="complete", expanded=False)
    with st.status("Quiz", expanded=True) as status:
        quiz.quiz_run(run_dir)
        status.update(label="Quiz: complete", state="complete", expanded=False)
    memory.contribute_run(run_dir, layout)
    return run_dir


def _replay(source: Path, layout: paths.Layout) -> Path:
    """Animate a completed run into the same seven boxes the live path fills.

    The boxes, their labels, their summaries, and their lines all come from
    `run_view`, so this is the live screen replayed rather than a second screen
    that resembles it. No model client is constructed on this path.
    """

    run_dir = replay.install_run(source, layout)
    stages = replay.replay_stages(run_dir)
    boxes: dict[str, Any] = {}
    logs: dict[str, Any] = {}
    lines: dict[str, list[str]] = {}

    def start(stage: replay.ReplayStage) -> None:
        if stage.absent:
            with st.status(f"{stage.label}: {stage.summary}", expanded=False, state="running"):
                st.caption("Pending — this stage has not written artifacts yet.")
            return
        boxes[stage.key] = st.status(stage.label, expanded=True)
        logs[stage.key] = st.empty()
        lines[stage.key] = []

    def line(stage: replay.ReplayStage, message: str) -> None:
        lines[stage.key].append(message)
        logs[stage.key].code("\n".join(lines[stage.key][-20:]), language=None)

    def end(stage: replay.ReplayStage) -> None:
        if stage.absent:
            return
        boxes[stage.key].update(
            label=f"{stage.label}: {stage.summary}",
            state=_status_state(stage.state),
            expanded=False,
        )

    replay.drive(stages, on_line=line, on_stage_start=start, on_stage_end=end)
    st.caption(f"Replayed from the committed run in {source}. No API calls were made.")
    return run_dir


def _replay_source(uploaded: Any, layout: paths.Layout) -> Path | None:
    """The committed run this upload is a replay of, matched by content hash."""

    if uploaded is None:
        return None
    digest = hashlib.sha256(uploaded.getvalue()).hexdigest()
    return replay.source_for_deck(digest, layout)


def main() -> None:
    st.set_page_config(page_title="Slide deck to study guide", layout="wide")
    st.title("Slide deck to study guide")
    st.caption("Image-path study guide with a text-path baseline")

    layout = paths.Layout()
    subjects = memory.list_subjects(layout)
    names = [subject.display_name for subject in subjects]
    lookup = {subject.display_name: subject.slug for subject in subjects}

    try:
        pointed_at = replay.replay_run_from_env(layout)
    except replay.ReplayError as error:
        st.error(str(error))
        pointed_at = None

    controls = st.columns([2, 2, 1])
    with controls[0]:
        selected_name = st.selectbox("Subject", names, index=None, placeholder="Choose a subject")
    with controls[1]:
        if pointed_at is None:
            uploaded = st.file_uploader("Deck (PDF)", type="pdf")
        else:
            uploaded = None
            st.caption(f"Replay mode: {pointed_at}")
    with controls[2]:
        st.write("")
        # A deck the committed run was produced from replays that run instead
        # of spending the API again, which is what the demo is pointed at.
        source = pointed_at or _replay_source(uploaded, layout)
        label = "Run pipeline" if source is None else "Generate study guide"
        ready = bool(source) or bool(selected_name and uploaded)
        run = st.button(label, type="primary", disabled=not ready)

    with st.expander("Create a subject"):
        display_name = st.text_input("New subject name")
        if st.button("Create subject"):
            try:
                created = memory.create_subject(display_name, layout)
            except (ValueError, memory.SubjectExists) as error:
                st.error(str(error))
            else:
                st.success(f"Created {created.display_name}. Choose it above.")

    if source is not None:
        with st.expander("Replay controls"):
            st.caption(
                "This deck matches a run that is already committed, so pressing "
                "the button replays that run from disk instead of calling the "
                "API. A rehearsal leaves a graded attempt behind, which makes "
                "the quiz open with its answer key already showing."
            )
            manifest_subject = replay.run_subject(source)
            if manifest_subject and st.button("Clear previous quiz attempts"):
                removed = replay.clear_attempts(manifest_subject, layout)
                st.success(f"Cleared {removed} attempt(s) for {manifest_subject}.")

    selected_slug = lookup.get(selected_name or "")
    run_dir = run_view.latest_run(layout, selected_slug) if selected_slug else None
    replaying = bool(run and source is not None)
    ran_this_request = replaying or bool(run and uploaded and selected_slug)
    if replaying and source is not None:
        try:
            run_dir = _replay(source, layout)
        except replay.ReplayError as error:
            st.error(str(error))
        else:
            # The run names its own subject. Honour it, so the quiz and the
            # attempt history below belong to the run that is on screen.
            summary = run_view.run_summary(run_dir)
            if summary is not None:
                selected_slug = summary.subject_slug
    elif source is not None:
        # A rerun after the animation has already played: show the same run
        # again without replaying it, and without needing a subject chosen.
        installed = replay.installed_run(source, layout)
        if installed is not None:
            run_dir = installed
            summary = run_view.run_summary(installed)
            if summary is not None and not selected_slug:
                selected_slug = summary.subject_slug
    if ran_this_request and not replaying and selected_slug:
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
        _render_comparison(run_dir)
        if selected_slug:
            _render_quiz(run_dir, selected_slug, layout)


if __name__ == "__main__":
    main()
