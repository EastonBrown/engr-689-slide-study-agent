# AGENTS.md

Working notes for agents in this repo. Project overview is in README.md.

## Agent skills

### Issue tracker

Issues live as GitHub issues on `EastonBrown/engr-689-slide-study-agent`,
managed with the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, each label string equal to its name. See
`docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` and `docs/adr/` at the repo root. See
`docs/agents/domain.md`. The stage-by-stage build contract assembled from both
is `docs/spec.md`; read it before implementing a stage.

## Checks

`python -m pytest` and `python -m mypy` from the repo root. Both are expected to
be clean before a commit. `src/` typechecks strictly; `tests/` is exempted from
the annotation requirements only.

Dependencies are pinned in `requirements.txt` (runtime) and
`requirements-dev.txt` (those plus `pytest` and `mypy`).
