# Golden run: Day 3 Principle, both paths

One complete run of `data/course/slides/Day3 Principle.pdf` (66 slides), both
the image path and the text path, plus the subject memory state it produced.
Committed per ADR 0004 so a collaborator and the demo have real artifacts
without spending tokens or needing a network. Produced headlessly, via
`study_agent.pipeline`, not by driving the interface.

## What's here

- `manifest.json` — per-stage token and cost totals, preflight, and per-path
  slide counts, for this run.
- `outline-image.json`, `outline-text.json` — the outline stage's output for
  each path.
- `review-image.md`, `review-text.md` — the lesson review each path wrote.
- `quiz.json` — the image-path quiz (ten questions; the text path is a
  baseline and never generates one).
- `pages-image/`, `pages-text/` — one `SlideNote` per slide per path.
- `pages-render/` — the rendered page image and extracted text for every
  slide.
- `research/` — the research-cache entries this run's outline pulled in.
- `memory/` — `subjects.json`, the `engr-689` subject's `profile.json`, and
  its `day3-principle` deck contribution. This is what the image path wrote
  to memory; the text path never contributes (ADR 0003).

## Degraded slides

The text path is a baseline, not a second system to chase to zero. 15 of its
66 slides came back degraded — the model itself flagging that the extracted
text gave it only a title, a fragment, or nothing at all — and those slides
are committed as they came back, not re-rolled until clean. The image path
has none: all 66 slides succeeded outright.

## `total_cost_usd` is a real lower bound, not the true total

This run was produced across several debugging passes: building it surfaced
five real bugs in the pipeline (a stale `output_config.format` field, an
unsupported array-schema shape, a missing `web_search` tool name, a
non-streaming call that the SDK refuses above a token threshold, and an empty
text content block on a textless slide), each fixed and re-verified against
the live API before the run continued.

One of those bugs was in the manifest itself: `page_reader` and `research`
each recompute their `stage_usage` row on every invocation, and a prior
version of that code *replaced* the row instead of adding to it. Every
debugging retry that touched those two stages silently dropped whatever a
previous invocation had already spent. That bug is fixed now (see the fix
alongside this run, with regression tests in `tests/test_page_reader.py` and
`tests/test_research.py`), but the fix cannot recover history that was
already overwritten before it landed — reconstructing it would mean spending
the money again just to re-measure it.

So: `manifest.json`'s `total_cost_usd` (currently $1.92) is real money that
was spent and is accounted for correctly from the point the fix landed
onward, but it understates what this specific committed run actually cost
across every debugging pass that built it. A single clean run with no bugs in
the way, per ADR 0001's own measurement on this deck, costs roughly $3.85 on
the image path and $1.30 on the text path — call it $5 as the honest estimate
for what one run like this costs going forward.

## Browsing this run locally

The interface (`app.py`) reads from `runs/<subject>/<deck>/<timestamp>/` and
`memory/`, both gitignored, not from `examples/golden/` directly. Replay mode
(issue #27) does the copying, so no manual setup is needed after a fresh
clone. Start the interface and select `data/course/slides/Day3 Principle.pdf`:
the upload is matched to this run by the sha256 in its `manifest.json`, and
the button replays it rather than calling the API.

`study_agent.replay.install_run` is what puts the files in place. It installs
the run under the subject, deck, and timestamp recorded in the manifest above,
writes the `latest` pointer, and copies `memory/` into place without
overwriting anything already there, since that tree is where a local user's
own attempts accumulate.

No `ANTHROPIC_API_KEY` is needed for any of this: viewing an existing run's
stages, summary, failures, and quiz never instantiates an API client, only a
live run does. Asserted in `tests/test_replay.py` by detonating
`llm.create_client` and `llm.load_api_key` for the whole replay path.
