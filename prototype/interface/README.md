# PROTOTYPE: the interface

Throwaway. Answers [issue #8](https://github.com/EastonBrown/engr-689-slide-study-agent/issues/8):
Streamlit or Gradio, and what is actually on the screen?

Nothing here is production code. There is no pipeline behind it, no network, no
persistence, no error handling. The one real thing is the page render, which
comes from the committed `data/course/slides/Day3 Principle.pdf` through pymupdf
at 150 DPI. Everything else is hand-written fake data in `fake_data.py`, shaped
to the locked schemas in `CONTEXT.md` so the screens are laid out against the
real contract.

## Run it

```
pip install streamlit gradio pymupdf
streamlit run prototype/interface/app.py
```

Three variants on one page, switchable with the floating bar at the bottom or
with `?variant=A`, `?variant=B`, `?variant=C`. The sidebar has a run-speed
slider (set it to "instant" when you just want to see the end state) and a
Reset. Neither the sidebar nor the bottom bar is part of any variant.

The Gradio probe is separate:

```
python prototype/interface/gradio_probe.py
```

## Verdict

**Streamlit, and variant A.** Variant A as built here is the settled screen
sequence, including the two sections added after the first round of reactions:
a SlideNote shown beside whichever cited slide you pick in the review, and a
failures section listing every slide with a `reader_note` next to its page
image. The text baseline gets exactly one screen, the comparison section, and is
otherwise an eval number.

B and C are kept below and in this branch as the alternatives that were rejected
and why, not as live options.

## The three variants

Each one answers "how is the work made visible" differently, and they disagree
about structure rather than about styling.

**A, pipeline console.** One long scrolling page. Seven stage boxes stack
vertically, open while running, fill with live per-slide detail, and collapse to
a one-line summary when done. Slide images appear small and inline in the
page-read log as evidence the slide was seen. The text baseline runs but never
gets a screen; it is a number in the eval table. Primary affordance is scroll.
Easiest thing to film in one unbroken take.

**B, slide workbench.** The deck is the interface. A 66-row filmstrip runs down
the left and lights up as each slide is read; clicking a row opens an inspector
with the page image beside its SlideNote, plus tabs for the text-path note on
the same slide and the raw JSON. Review, quiz, and memory are top-level tabs.
Primary affordance is pick a slide and inspect it. The ablation is a tab on
every slide instead of a separate screen, and the memory tab is the only place
the two-axis exposure and performance table appears.

**C, split ablation.** The screen is cut down the middle for the whole run.
Image path left, text path right, in lockstep: progress bar beside progress bar,
note beside note, review beside review. A scoreboard across the top counts
figure-only facts recovered, 3 of 4 against 0 of 4, with slide 10 reported as
partial on both sides. The slide image sits in the gutter so both readings point
at the same page. Primary affordance is comparison.

## Streamlit versus Gradio

`gradio_probe.py` rebuilds the hardest screen, variant B's live per-slide read
with a clickable slide list and the image beside the note, in Gradio 6, so the
comparison is measured rather than asserted. Both frameworks install clean on
Python 3.14.2 here, so availability decides nothing.

What building it twice actually turned up:

1. **Live per-stage detail.** Streamlit's `st.status` is a collapsible box that
   owns its own live region, so seven stages can each log into their own box and
   collapse to a summary line. Gradio has one progress bar per event, and live
   updates are a generator yielding a fixed tuple of pre-declared outputs. Every
   widget you want to move during a run has to be in the `outputs` list and
   re-emitted on every single yield. Seven stages that expand, log, and collapse
   has no Gradio primitive. This is the whole "demonstrate the effort" ask, and
   it is where the gap is widest.
2. **The 66-row filmstrip.** In Streamlit it is a `for` loop of buttons inside a
   fixed-height scroll container, each carrying its own status marker. Gradio
   declares components at build time, so it is either 66 components with 66
   click handlers or a dropdown. The probe used a dropdown and lost the
   row-by-row status entirely.
3. **Images.** `st.image` takes bytes and caches them in memory. `gr.Image`
   wants a path, so `page_file()` in the probe writes every rendered page to a
   temp directory first. Minor, but it is 66 files of avoidable I/O for a screen
   that is meant to feel instant.
4. **The quiz flow.** Streamlit's `session_state` carries answers, grade, and
   attempt count with no plumbing. Gradio needs `gr.State` threaded through
   every handler.
5. **API churn.** `show_download_button` on `gr.Image` was removed in Gradio 6
   and had to be dropped. Streamlit 1.62 deprecated `use_container_width` in
   favour of `width="stretch"`. Both churn; neither decides anything.

Gradio wins on exactly one thing that matters here: `demo.launch(share=True)`
gives a public URL for free. Whether a live hosted demo happens at all is still
in the map's fog, and a tunnel is not worth the four costs above.

**One honest cost of Streamlit,** found while building A: the whole script
reruns on every widget interaction, so an animated run held only in memory has
to be re-triggered or cached. The real app must not hold run results in memory.
It has to write each stage to disk and have the UI read from disk. ADR 0004
already requires exactly that, so the constraint costs nothing new, but it is a
constraint the interface now depends on rather than merely benefits from.

## Files

| File | What it is |
|---|---|
| `app.py` | Entry point, variant routing, sidebar controls |
| `shared.py` | Page render, switcher bar, session state, grader |
| `fake_data.py` | Hand-written notes, review, quiz, topics, research log |
| `variant_a.py` | Pipeline console |
| `variant_b.py` | Slide workbench |
| `variant_c.py` | Split ablation |
| `gradio_probe.py` | Variant B's hardest screen rebuilt in Gradio, as evidence |

## Acknowledgment

The slide images this prototype renders are the ENGR 689 instructors' material.
See `data/course/README.md`.
