"""PROTOTYPE. The same screen as variant B, built in Gradio, as decision evidence.

The Streamlit versus Gradio argument is easy to make in the abstract and worth
nothing there. This builds the single hardest screen twice: a live-updating
per-slide read with a filmstrip you can click, the page image beside the
structured note, and the text path behind a tab. Whatever this file costs in
awkwardness compared to `variant_b.py` is the real answer.

Run:  python prototype/interface/gradio_probe.py
"""

import os
import sys
import tempfile
import time

import gradio as gr

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fake_data as fd  # noqa: E402
from shared import REPO_ROOT  # noqa: E402

_TMP = os.path.join(tempfile.gettempdir(), "engr689-proto-pages")
os.makedirs(_TMP, exist_ok=True)


def page_file(n, dpi=150):
    """Gradio wants a path, not bytes, so every page has to hit disk first."""
    out = os.path.join(_TMP, f"{n:04d}.png")
    if not os.path.exists(out):
        import pymupdf

        doc = pymupdf.open(os.path.join(REPO_ROOT, fd.DECK_PATH))
        doc[n - 1].get_pixmap(dpi=dpi).save(out)
        doc.close()
    return out


def note_md(n, path):
    note = fd.slide_note(n, path)
    lines = [f"### Slide {n} ({path} path)"]
    if note["reader_note"]:
        lines.append(f"**reader_note:** {note['reader_note']}")
    lines.append(f"*page_role:* `{note['page_role']}`")
    lines.append(f"**Reading.** {note['reading'] or '(empty)'}")
    lines.append("**Visuals.**")
    if not note["visuals"]:
        lines.append("- none")
    for v in note["visuals"]:
        lines.append(f"- `{v['kind']}` {v['description']}")
        if v["assertion"]:
            lines.append(f"  - asserts: *{v['assertion']}*")
    lines.append("**Concepts.**")
    if not note["concepts"]:
        lines.append("- none")
    for c in note["concepts"]:
        lines.append(f"- {c['name']} (`{c['status']}`) {c['why_it_matters']}")
    return "\n\n".join(lines)


def run(speed, progress=gr.Progress()):
    """Streaming fake run. Yields the four outputs on every slide."""
    log = []
    for n in progress.tqdm(range(1, fd.SLIDE_COUNT + 1), desc="Page read"):
        note = fd.slide_note(n, "image")
        log.append(
            f"slide {n:>2}: {len(note['visuals'])} visual, {len(note['concepts'])} concept"
            + (" DEGRADED" if note["reader_note"] else "")
        )
        time.sleep(speed)
        yield ("\n".join(log[-10:]), page_file(n), note_md(n, "image"), note_md(n, "text"))


def select(n):
    return page_file(int(n)), note_md(int(n), "image"), note_md(int(n), "text")


with gr.Blocks(title="PROTOTYPE gradio probe") as demo:
    gr.Markdown(
        "## Gradio probe\n"
        "The variant B screen, rebuilt in Gradio. Prototype only. "
        "Compare the friction here against `variant_b.py`."
    )
    with gr.Row():
        gr.Dropdown(fd.SUBJECTS, value=fd.SUBJECTS[0], label="Subject")
        gr.File(label="Deck (PDF)", file_types=[".pdf"])
        speed = gr.Slider(0.001, 0.15, value=0.02, label="Fake run speed (s per slide)")
        go = gr.Button("Run", variant="primary")

    with gr.Row():
        with gr.Column(scale=1):
            picker = gr.Dropdown(
                [str(n) for n in range(1, fd.SLIDE_COUNT + 1)],
                value="61", label="Slide",
            )
            gr.Markdown("Slides carrying a hand-labeled figure-only fact: "
                        + ", ".join(str(n) for n in sorted(fd.FIGURE_ONLY)))
            log_box = gr.Textbox(label="Page read log", lines=12, max_lines=12)
        with gr.Column(scale=1):
            img = gr.Image(value=page_file(61), label="Rendered page, 150 DPI")
        with gr.Column(scale=1):
            with gr.Tabs():
                with gr.Tab("Image path"):
                    img_note = gr.Markdown(note_md(61, "image"))
                with gr.Tab("Text path"):
                    txt_note = gr.Markdown(note_md(61, "text"))

    go.click(run, inputs=[speed], outputs=[log_box, img, img_note, txt_note])
    picker.change(select, inputs=[picker], outputs=[img, img_note, txt_note])

if __name__ == "__main__":
    demo.launch()
