# Results

Protocol is locked by [ADR 0006](../docs/adr/0006-eval-protocol-and-results-table.md).
Labels are in [`figure-only-facts.json`](figure-only-facts.json). Nothing below
is filled in yet.

Run scored: `<runs/<subject>/day3-principle/<timestamp>>`
Scored by: Easton Brown, by hand
Date scored:

## Figure-only fact recovery, Day 3 deck (single run)

A hit is the fact appearing anywhere in that slide's `SlideNote`, in any field.
The Field column records where it landed for the image path.

| Fact | Slide(s) | Image | Text | Field |
| --- | --- | --- | --- | --- |
| Russell and Norvig sensors/actuators | 61 | | | |
| CLIP dominance in the bar chart | 28, 48 | | | |
| Generation composes, retrieval cannot | 55-56 | | | |
| **Total** | | **/3** | **/3** | |
| Pinhole geometry (known-weak case) | 10 | | | |

The interface shows this row too. It reads the scores from
`figure-only-facts.json`, where a scored fact carries
`"scored": {"image": true, "text": false}`, and shows "scored by hand" until
every labelled fact carries one. Filling the table above means filling that
field in the same pass.

Slide 10 sits outside the headline denominator on purpose. Its labels extract,
so a hit there does not mean the text path recovered the spatial relation that
is the actual content of the slide.

## Repeatability, image path, 5 re-reads per labeled slide

| Slide | Hits |
| --- | --- |
| 61 | /5 |
| 28 | /5 |
| 55-56 | /5 |
| 10 | /5 |

## Citation accuracy, image path only

| Check | Result |
| --- | --- |
| Quiz `slide_citations` supported by the cited slide, by hand | /10 |
| `verbatim_spans` found verbatim in that page's extracted text | / |

This is a hallucination check on the image path, not a comparison. ADR 0002
makes `verbatim_spans` degenerate by construction on the text path, and ADR 0005
gives the text path no quiz to cite from.

## Not measured

Concept overlap against the instructors' Quiz 3 was considered and dropped. At a
sample of one quiz there is no defensible rule for when a generated question and
an instructor question cover the same concept, and an unfalsifiable metric is
worse on the results slide than an absent one.
