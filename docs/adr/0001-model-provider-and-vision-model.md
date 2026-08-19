# ADR 0001: Model provider and vision model

- Status: accepted
- Date: 2026-08-19
- Resolves: [Choose the model provider and vision model](https://github.com/EastonBrown/engr-689-slide-study-agent/issues/2)

## Context

Every pipeline stage needs a model behind it: the page reader (vision over
rendered slide images), the outline stage, the shallow research step, the review
writer, the quiz generator, and the grader. The build window is two days, the
repo is public, and collaborators are joining on other machines.

Credentials on hand: one personal Anthropic API key belonging to the project
owner. The course handed out nothing. No OpenAI or Gemini key is available. On
the owner's machine at the time of this decision, no credential of any kind was
configured in the environment.

## Decision

**One provider, Anthropic, through the Claude API, for every stage.**

**One model, `claude-opus-5`, for every stage.** Depth is controlled with
`output_config.effort` rather than by swapping models: `low` for the per-slide
page reader, `high` for the outline, review writer, and quiz generator.
Adaptive thinking (`thinking: {type: "adaptive"}`) everywhere, which is the
default on this model.

**The shallow research step uses the hosted `web_search_20260209` server tool**,
not a scraper. It is declared in `tools` and runs on Anthropic's infrastructure;
results come back with citations attached. Cap it with `max_uses` per request
and cache every result to disk so demo runs replay without network.

**Page images are sent one per request**, not batched, with client-side
concurrency across slides.

**The key lives in `ANTHROPIC_API_KEY`**, read from the environment or a
gitignored `.env`. It is never committed. Collaborators supply their own.

## Why not a cheaper reader model

The obvious cost move is Claude Haiku 4.5 on the 66 page images and a stronger
model only for writing. Rejected, and not on cost grounds.

Claude models fall into two image-resolution tiers. Claude 4.7 and later, which
includes `claude-opus-5` and `claude-sonnet-5`, are high-resolution: 2576 px
long edge, 4784 visual tokens per image. Every other model, Haiku 4.5 included,
is standard tier: 1568 px long edge, 1568 visual tokens. A slide rendered at
2000x1125 costs 2952 visual tokens on the high-resolution tier and is passed
through unresized; the same slide handed to Haiku 4.5 is downscaled to roughly
1456x819 and capped at 1560 visual tokens, a little over half the detail.

The entire premise of this project is that architecture diagrams, plots, and
equations on a slide carry meaning that text extraction discards. Reading those
pages at half resolution attacks the one claim the demo exists to make. The
cheaper reader is a false economy here.

## Why one model rather than a cheap-reader / strong-writer split

Cost is not a constraint (see below), so the split would buy nothing but a
second set of prompts, a second set of failure modes, and a second thing to
explain on Friday. One model is one auth path, one SDK surface, one prompt
style, and one behaviour to characterise in the limitations section.

## Why one image per request

The API accepts up to 600 images per request on a 1M-context model, so all 66
slides would fit in one call. Three reasons not to:

1. Any request carrying more than 20 image blocks triggers a stricter per-image
   dimension limit, and staying under it means resizing every page so neither
   dimension exceeds 2000 px. That claws back the resolution the tier choice was
   made to protect.
2. The page reader produces structured per-slide notes. One request per slide
   maps to that output shape directly, with no risk of the model losing track of
   which page it is describing.
3. A malformed or refused page fails alone and is retried alone, instead of
   taking the other 65 with it.

## Cost, for the record

Measured against a 66-slide deck rendered at 150 DPI (2000x1125 px per page).

| Stage | Input | Output | Cost |
|---|---|---|---|
| Page reader, 66 slides | ~221K tokens | ~33K tokens | ~$1.94 |
| Outline, review, quiz | ~140K tokens | ~30K tokens | ~$1.45 |
| Research, ~15 lookups | search fee plus tokens | | ~$0.45 |
| **Image path, full run** | | | **~$3.85** |
| **Text path, full run** | ~50K tokens | ~30K tokens | **~$1.30** |

At `claude-opus-5` rates of $5 per million input tokens and $25 per million
output tokens, plus web search at $10 per 1,000 searches. Roughly 25 full image
path demo runs per $100. That is affordable on a personal key for a two-day
sprint, which is why the capability argument above was allowed to decide.

## Consequences

- A single hard dependency on one vendor and one API key. If the key is
  exhausted or rate limited during the Friday demo, there is no fallback path.
  Cached artifacts from prior runs are the mitigation: the demo must be able to
  replay a completed run from disk without calling the API at all.
- Collaborators each need their own key. No shared credential is committed.
- The text-extraction baseline runs against the same model, so the image
  versus text comparison isolates the input modality rather than confounding it
  with a model change.
- Slide renders are pinned at 150 DPI. Changing the render DPI changes both the
  token cost and whether images are downscaled, so it is a decision with a
  price attached, not a knob.

## Sources

- Vision limits, resolution tiers, and visual-token arithmetic:
  https://platform.claude.com/docs/en/build-with-claude/vision
- Web search tool, versions, and the $10 per 1,000 searches rate:
  https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool
- Model IDs, context windows, and per-token pricing: the bundled `claude-api`
  agent skill, model table cached 2026-06-24.
