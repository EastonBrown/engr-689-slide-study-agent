# Course material

Lecture decks and quizzes from ENGR 689 (SPTP: Multimodal LLM Agents),
Texas A&M, fall 2026. **This is the instructors' material, not mine.** It is
committed here because the pipeline is built and evaluated against it, and
because the eval compares generated questions against the instructors' own
quizzes. Day 1 and Day 2 were taught by one instructor as a continuous thread;
Day 3 is a different instructor and restarts from computer vision.

Files are unmodified originals as posted to the course.

## Slides

`slides/`, all exported from PowerPoint at 960x540 points (16:9).

| File | Slides | Embedded images | Median extracted text per slide |
|---|---|---|---|
| `Day1 Principle.pdf` | 65 | 229 | 142 chars |
| `Day1 Tool.pdf` | 38 | 37 | 97 chars |
| `Day2 Principle.pdf` | 62 | 208 | 279 chars |
| `Day2 Tool.pdf` | 55 | 55 | 115 chars |
| `Day3 Principle.pdf` | 66 | 138 | 157 chars |

286 slides total, 66 of them in the Day 3 deck the eval targets.
The Day 3 deck has 65 covered slides: render preflight detects slide 23 as a
superseded build-up frame whose surviving page is slide 24. The other four
course decks have no superseded frames.

### Nothing hostile about them

Checked deliberately, because each of these would have cost a day:

- **Not scanned.** Every deck carries a real text layer, so the text-only
  baseline is a fair comparison rather than a straw man.
- **One page size throughout.** No mixed orientation, no odd aspect ratio.
  Page-image rendering needs one DPI setting, not a per-deck one.
- **No animation duplicates.** Zero consecutive pages share identical extracted
  text across all five decks, so builds are not exported one-fragment-per-page.
  Slide numbers in the PDF are the slide numbers the instructor showed.
- Four slides carry almost no text (Day 3 slides 6, 12, 56, 66). Slide 56 has
  none at all, which is the point of the eval below rather than a defect.

Median text per slide is low across the board, 97 to 279 characters. The decks
are visual. That is the premise of the project and it holds up on measurement.

## Quizzes

`quizzes/`, the instructors' own quizzes over these decks. Quiz 1 covers Days 1
to 2, Quiz 3 covers Day 3. Three pages, three pages, and two pages, all text,
no figures.

These are the ground truth for the concept-overlap metric: which slides and
concepts the instructors chose to test, against which ones the generated quiz
targets.

## The four figure-only facts in the Day 3 deck

Facts that exist in the slide image and survive poorly or not at all through
text extraction. These are the hand-labeled cases the eval protocol counts
recovery against. Slide numbers are 1-based and refer to `Day3 Principle.pdf`.

| # | Slide | Fact | What text extraction returns |
|---|---|---|---|
| 1 | 61 | The Russell and Norvig definition: an agent perceives its environment through **sensors** and acts on it through **actuators** | Only "Agentic AI" and the follow-on line "This definition holds for embodied and digital agents". The definition itself is inside the figure. Nothing of environment, sensors, or actuators survives. |
| 2 | 28, repeated at 48 | CLIP-style multimodal learning is by far the most used vision encoder in real multimodal LLMs, far above DINOv2 and VQ-VAE | The axis label "Popularity of different vision encoders in Multimodal LLMs" and the five family names. The ranking lives entirely in the bar heights. |
| 3 | 55 to 56 | Generation composes concepts and retrieval cannot: DALL-E 2 renders "a cup of cat", while an image search for the same phrase returns cats sitting in cups | Slide 55 gives the three captions with no images to compare. Slide 56, the retrieval side of the comparison, extracts to **zero characters**. |
| 4 | 10 | The three directions form a pinhole-camera geometry: recognition and generation are inverses across the projection surface, reconstruction runs from projection back to scene | Weakest of the four. The labels do extract. What is lost is the spatial relation between them, which is the entire content of the slide. |

Case 4 is honestly the weak one and should be reported as such rather than
counted alongside the other three. Cases 1 and 3 are the strong demonstrations:
in both, the load-bearing content extracts to nothing.

## Acknowledgment

All slides and quizzes are the work of the ENGR 689 instructors. Figures inside
the decks carry their own credit lines, including A. Torralba, P. Isola, and
W. T. Freeman, *Foundations of Computer Vision* (Day 3 slides 10 and 55).
