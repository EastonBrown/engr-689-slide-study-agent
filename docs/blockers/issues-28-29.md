# Blocker Note: Issues #28 and #29

Date: 2026-08-20
Branch: `codex/remaining-pipeline`

## #28 Full 66-slide run committed as examples/golden

Blocked by missing model credentials.

The Day 3 Principle source deck is present at:

`data/course/slides/Day3 Principle.pdf`

Current environment evidence:

- `ANTHROPIC_API_KEY` is not set.
- `examples/golden/` does not exist.
- Existing local Day 3 run directories under `runs/engr-689/day3-principle/` are render-only.
- Their manifests show `completed_stages` only at `render`, `quiz_questions: 0`, and `total_cost_usd: 0.0`.

The #28 acceptance criteria require a real full 66-slide end-to-end run on both image and text paths, with every page note, both outlines, research entries, both reviews, `quiz.json`, memory state, and real per-stage token/cost totals. Producing those artifacts without the model key would require faking model outputs or hand-writing artifacts, which would violate the issue acceptance criteria.

Unblock steps:

1. Set `ANTHROPIC_API_KEY` in the shell running the pipeline.
2. Run the Day 3 Principle deck headlessly through `--quiz`.
3. Preserve any degraded slide outputs rather than re-rolling them clean.
4. Copy the completed run directory and the memory state it produced into `examples/golden/`.
5. Verify replay works with no key set.
6. Run `python -m pytest` and `python -m mypy src` from the repo root.
7. Commit only `examples/golden/`; keep root `runs/` and `memory/` ignored.

## #29 Score the eval by hand and fill eval/results.md

Blocked by #28 and human scoring. Issue #29 also lists #18 as a dependency; #18 is satisfied on this branch by commit `5b686f7` (`eval/score_spans.py`).

Issue #29 is labeled `ready-for-human` and requires hand judgments:

- eight figure-only recovery judgments with hit fields
- slide 10 known-weak case separated from the headline denominator
- five image-path re-reads per labeled slide
- hand-scored quiz citation accuracy
- `eval/score_spans.py` run over the committed golden run
- `eval/results.md` filled from those results with no empty cells
- anything outside the instrumentation reported as unmeasured rather than estimated

Without the committed #28 golden run, there is no authoritative source for the eval table. Without the human judgment pass, filling the table would be invented data.
