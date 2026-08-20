"""PROTOTYPE fake data. Hand-written, not produced by any pipeline.

Shapes follow the locked schemas in CONTEXT.md (SlideNote, Question, Topic) so
the screens are laid out against the real contract rather than a convenient one.
Content for the seven detailed slides comes from `Day3 Principle.pdf` and from
the four figure-only facts pinned in `data/course/README.md`. Every other slide
gets a filler note so the run has a realistic length of 66.
"""

DECK_PATH = "data/course/slides/Day3 Principle.pdf"
DECK_SLUG = "day3-principle"
SLIDE_COUNT = 66

SUBJECTS = ["ENGR 689 Multimodal LLM Agents", "ENGR 602 Systems Engineering"]

TOPICS = [
    "Computer vision as a field",
    "Vision encoders",
    "Contrastive image-text pretraining",
    "Vision language model architectures",
    "Compositionality and generation",
    "Agent definitions",
]

# The four hand-labeled figure-only facts, keyed by the slide that carries them.
FIGURE_ONLY = {
    61: "Russell and Norvig: an agent perceives its environment through sensors and acts through actuators",
    28: "CLIP-style multimodal learning is by far the most used vision encoder, far above DINOv2 and VQ-VAE",
    55: "Generation composes concepts and retrieval cannot: DALL-E 2 renders a cup of cat",
    10: "The three directions form a pinhole-camera geometry (weak case, the labels do extract)",
}


def _note(n, role, title, reading, visuals, concepts, spans, topic, note=None):
    return {
        "slide_number": n,
        "page_role": role,
        "title": title,
        "reading": reading,
        "visuals": visuals,
        "concepts": concepts,
        "verbatim_spans": spans,
        "reader_note": note,
        "topic": topic,
    }


DETAILED = {
    1: _note(
        1, "title", "Multimodal LLM Agents",
        "Course title page for Day 3, naming the day's subject as large vision "
        "and language models and giving the instructor as Cheng Zhang, "
        "co-taught with Prof. Yu Zhang.",
        [{"kind": "decorative",
          "description": "Maroon banner across the top third of the page",
          "assertion": None, "relates_to_slides": []}],
        [],
        ["Day 3: Large Vision and Language Models"],
        "Computer vision as a field",
    ),
    10: _note(
        10, "content", "Three representative directions",
        "The page lays out three directions in computer vision, recognition, "
        "reconstruction, and generation, arranged around a projection surface "
        "that separates a 3D or 4D scene from an image or video.",
        [{"kind": "diagram",
          "description": "A pinhole-camera schematic. A tree in the world sits left of a "
                         "labelled projection surface and its image sits right of it. Arrow 1 "
                         "(recognition) runs image to scene, arrow 3 (generation) runs scene to "
                         "image, arrow 2 (reconstruction) runs the projection back to the scene.",
          "assertion": "Recognition and generation are inverses across the projection surface, "
                       "and reconstruction runs from the projection back to the scene.",
          "relates_to_slides": [11, 12]}],
        [{"name": "Projection surface", "status": "explained_here",
          "why_it_matters": "It is the axis the three directions are defined against."},
         {"name": "Reconstruction", "status": "named_only",
          "why_it_matters": "Named as direction 2 but never unpacked on this page."}],
        ["Three representative directions", "Projection surface"],
        "Computer vision as a field",
    ),
    28: _note(
        28, "content", "Variants of vision encoder",
        "Five families of vision encoder are listed with a representative model "
        "for each, and a bar chart ranks how often each family is used inside "
        "real multimodal LLMs.",
        [{"kind": "chart",
          "description": "Bar chart, y-axis 'Popularity of different vision encoders in "
                         "Multimodal LLMs'. The multimodal learning bar towers over the rest. "
                         "DINOv2 and VQ-VAE are short bars near the floor.",
          "assertion": "CLIP-style multimodal learning is by far the most used vision encoder "
                       "in practice, far above DINOv2 and VQ-VAE.",
          "relates_to_slides": [48]}],
        [{"name": "Masked modeling", "status": "named_only",
          "why_it_matters": "Given only as MAE, He et al., with no account of the objective."},
         {"name": "Self-distillation", "status": "named_only",
          "why_it_matters": "Given only as DINO, Caron et al."},
         {"name": "Contrastive multimodal learning", "status": "explained_here",
          "why_it_matters": "The family the rest of the lecture builds on."}],
        ["Variants of vision encoder", "Self-distillation", "Auto-encoding"],
        "Vision encoders",
    ),
    48: _note(
        48, "content", "Variants of vision encoder",
        "The encoder-family slide is shown again as a callback before the "
        "architecture section.",
        [{"kind": "chart",
          "description": "The same popularity bar chart as slide 28.",
          "assertion": "Repeat of the ranking asserted on slide 28.",
          "relates_to_slides": [28]}],
        [{"name": "Contrastive multimodal learning", "status": "explained_here",
          "why_it_matters": "Repeated to motivate the architecture section."}],
        ["Variants of vision encoder"],
        "Vision encoders",
    ),
    55: _note(
        55, "content", "Compositionality in large pre-trained models",
        "Three captions, 'A cup of coffee', 'A cat', and 'A cup of cat', sit "
        "above generated images credited to DALL-E 2.",
        [{"kind": "comparison",
          "description": "Three DALL-E 2 outputs under their prompts. The third renders a "
                         "literal cup made of cat, a composition with no training example.",
          "assertion": "A generative model composes two familiar concepts into an unfamiliar one.",
          "relates_to_slides": [56]}],
        [{"name": "Compositionality", "status": "explained_here",
          "why_it_matters": "The property that separates generation from retrieval."}],
        ["Compositionality in large pre-trained models", "A cup of cat", "DALL-E 2"],
        "Compositionality and generation",
    ),
    56: _note(
        56, "content", None,
        "The page is a full-bleed screenshot with no text of its own. It shows "
        "an image search for the phrase from the previous slide.",
        [{"kind": "screenshot",
          "description": "An image-search results grid for 'a cup of cat'. Every result is a "
                         "photograph of a cat sitting inside a cup or mug. None is a cup made "
                         "of cat.",
          "assertion": "Retrieval cannot compose. Asked for the same phrase it returns the "
                       "nearest thing that already exists.",
          "relates_to_slides": [55]}],
        [{"name": "Retrieval versus generation", "status": "explained_here",
          "why_it_matters": "The contrast is the whole argument for generative models here."}],
        [],
        "Compositionality and generation",
    ),
    61: _note(
        61, "content", "Agentic AI",
        "The page gives a textbook definition of an agent inside a figure, with "
        "one line of prose underneath noting the definition's reach.",
        [{"kind": "diagram",
          "description": "The Russell and Norvig agent loop. An agent box sits inside an "
                         "environment box, taking percepts in through sensors and acting back "
                         "on the environment through actuators.",
          "assertion": "An agent is anything that perceives its environment through sensors and "
                       "acts on that environment through actuators.",
          "relates_to_slides": [62]}],
        [{"name": "Sensors", "status": "explained_here",
          "why_it_matters": "One half of the definition of an agent."},
         {"name": "Actuators", "status": "explained_here",
          "why_it_matters": "The other half."},
         {"name": "Embodied agent", "status": "named_only",
          "why_it_matters": "Claimed to be covered by the definition, never described."}],
        ["Agentic AI", "This definition holds for embodied and digital agents"],
        "Agent definitions",
    ),
}

_FILLER_TOPIC = [
    "Computer vision as a field", "Vision encoders",
    "Contrastive image-text pretraining", "Vision language model architectures",
    "Compositionality and generation", "Agent definitions",
]


def slide_note(n, path="image"):
    """One SlideNote for slide n. The text path is deliberately thinner."""
    if n in DETAILED:
        note = dict(DETAILED[n])
        note["visuals"] = [dict(v) for v in note["visuals"]]
    else:
        topic = _FILLER_TOPIC[(n // 11) % len(_FILLER_TOPIC)]
        note = _note(
            n, "content", f"Slide {n}",
            f"Placeholder reading for slide {n}. The prototype writes real notes "
            f"only for the seven slides the eval turns on.",
            [{"kind": "diagram", "description": f"Placeholder figure on slide {n}",
              "assertion": f"Placeholder assertion for slide {n}",
              "relates_to_slides": []}],
            [{"name": f"Concept {n}a", "status": "explained_here",
              "why_it_matters": "Placeholder."}],
            [f"Slide {n} heading"],
            topic,
        )
    if path == "text":
        note = dict(note)
        note["visuals"] = []
        note["reading"] = "Text-path reading: " + note["reading"].split(".")[0] + "."
        if n == 56:
            note["reading"] = ""
            note["reader_note"] = "Extracted text was empty. Nothing to read."
            note["concepts"] = []
            note["verbatim_spans"] = []
    if n == 33 and path == "image":
        note = dict(note)
        note["reader_note"] = "Model returned malformed JSON twice. Slide read as degraded."
    return note


REVIEW_MD = """\
## What Day 3 covered

Day 3 restarts the course from computer vision and walks up to vision language
models, ending on the definition of an agent that the rest of the course uses.

### Computer vision as a field

The deck opens by placing three directions on one geometry. Recognition and
generation are inverses across a projection surface, and reconstruction runs
from the projection back to the scene [slide 10]. The arrangement, not the three
labels, is the content of that page.

### Vision encoders

Five families are named with one representative model each: ViT for supervised
learning, MAE for masked modeling, VQ-VAE for auto-encoding, DINO for
self-distillation, and CLIP-style multimodal learning [slide 28]. The lecture
does not treat them as equals. In real multimodal LLMs, CLIP-style encoders are
used far more than DINOv2 or VQ-VAE, and the deck makes that point in a bar
chart rather than in prose [slides 28, 48].

### Compositionality

A generative model can compose two familiar concepts into an unfamiliar one.
DALL-E 2 renders "a cup of cat" [slide 55]. Retrieval asked for the same phrase
returns photographs of cats sitting in cups, because it can only return what
already exists [slide 56].

### Agents

An agent perceives its environment through sensors and acts on it through
actuators [slide 61]. The deck notes that this holds for embodied and digital
agents alike.
"""

TEXT_REVIEW_MD = """\
## What Day 3 covered

Day 3 covers computer vision and vision language models.

### Computer vision as a field

The deck lists three representative directions: recognition, reconstruction, and
generation [slide 10].

### Vision encoders

Five families are named with a representative model each: ViT, MAE, VQ-VAE,
DINO, and multimodal learning [slide 28]. The slide is repeated later
[slide 48].

### Compositionality

The deck gives three captions, "A cup of coffee", "A cat", and "A cup of cat",
credited to DALL-E 2 [slide 55].

### Agents

The deck states that the definition holds for embodied and digital agents
[slide 61].
"""

QUIZ = [
    {"question_id": "day3-principle-q01",
     "stem": "In the pinhole-camera arrangement the deck uses to organise computer vision, "
             "what is the relationship between recognition and generation?",
     "options": ["They are inverses across the projection surface",
                 "They are two names for the same operation",
                 "Generation is a special case of recognition",
                 "They operate on different sensors"],
     "correct_index": 0,
     "explanation": "The diagram puts the scene on one side of the projection surface and the "
                    "image on the other. Recognition runs one way across it, generation the other.",
     "distractor_rationale": [None,
                              "The deck separates them by direction, so they cannot be one operation.",
                              "Nothing in the diagram nests one inside the other.",
                              "Sensors belong to the agent slide, not this one."],
     "slide_citations": [10], "topic": "Computer vision as a field", "source": "visual"},
    {"question_id": "day3-principle-q02",
     "stem": "Among the vision encoder families the deck names, which is used most often inside "
             "real multimodal LLMs?",
     "options": ["VQ-VAE style auto-encoding", "DINO style self-distillation",
                 "CLIP style multimodal learning", "MAE style masked modeling"],
     "correct_index": 2,
     "explanation": "The popularity chart puts the multimodal learning bar far above every other "
                    "family. The ranking is in the bar heights, not in the slide text.",
     "distractor_rationale": ["A short bar near the floor of the same chart.",
                              "Also near the floor, well below multimodal learning.",
                              None,
                              "Named on the slide but not the leader in the chart."],
     "slide_citations": [28, 48], "topic": "Vision encoders", "source": "visual"},
    {"question_id": "day3-principle-q03",
     "stem": "What does the deck use the phrase 'a cup of cat' to demonstrate?",
     "options": ["That prompt wording is ambiguous",
                 "That generation composes concepts and retrieval cannot",
                 "That DALL-E 2 fails on unusual prompts",
                 "That image search indexes captions rather than pixels"],
     "correct_index": 1,
     "explanation": "The generated image is a cup made of cat. The retrieval results for the same "
                    "phrase are cats sitting in cups, because retrieval returns only what exists.",
     "distractor_rationale": ["The deck treats the phrase as well defined, not ambiguous.",
                              None,
                              "The generation succeeds, which is the point.",
                              "The indexing mechanism is never discussed."],
     "slide_citations": [55, 56], "topic": "Compositionality and generation", "source": "visual"},
    {"question_id": "day3-principle-q04",
     "stem": "According to the definition the deck gives, an agent acts on its environment through:",
     "options": ["Actuators", "Percepts", "Sensors", "Policies"],
     "correct_index": 0,
     "explanation": "Perception comes in through sensors and action goes out through actuators.",
     "distractor_rationale": [None,
                              "Percepts are what comes in, not the channel action goes out through.",
                              "Sensors are the input half of the definition.",
                              "Policies are not part of this definition."],
     "slide_citations": [61], "topic": "Agent definitions", "source": "visual"},
    {"question_id": "day3-principle-q05",
     "stem": "Which representative model does the deck attach to masked modeling?",
     "options": ["DINO", "MAE", "ViT", "VQ-VAE"],
     "correct_index": 1,
     "explanation": "The encoder-family list pairs masked modeling with MAE.",
     "distractor_rationale": ["DINO is paired with self-distillation.", None,
                              "ViT is paired with supervised learning.",
                              "VQ-VAE is paired with auto-encoding."],
     "slide_citations": [28], "topic": "Vision encoders", "source": "prose"},
    {"question_id": "day3-principle-q06",
     "stem": "The deck says its definition of an agent holds for which kinds of agent?",
     "options": ["Only embodied agents", "Only digital agents",
                 "Embodied and digital agents", "Only agents with a language model"],
     "correct_index": 2,
     "explanation": "The line under the figure states that the definition holds for embodied and "
                    "digital agents.",
     "distractor_rationale": ["The slide explicitly covers both.",
                              "The slide explicitly covers both.", None,
                              "Language models are not part of the definition."],
     "slide_citations": [61], "topic": "Agent definitions", "source": "prose"},
    {"question_id": "day3-principle-q07",
     "stem": "In the three-directions diagram, what does reconstruction run between?",
     "options": ["Image and caption", "Projection back to the scene",
                 "Scene and scene", "Encoder and decoder"],
     "correct_index": 1,
     "explanation": "Reconstruction is the arrow from the projection back into the 3D or 4D scene.",
     "distractor_rationale": ["Captions do not appear on this slide.", None,
                              "It crosses the projection surface, so the endpoints differ.",
                              "Encoders and decoders come later in the deck."],
     "slide_citations": [10], "topic": "Computer vision as a field", "source": "visual"},
    {"question_id": "day3-principle-q08",
     "stem": "Why does the deck show an image-search result grid immediately after the DALL-E 2 "
             "outputs?",
     "options": ["To credit the source of the generated images",
                 "To show retrieval returning the nearest existing thing instead of the composition",
                 "To compare image resolution between the two systems",
                 "To show that search engines are faster than generation"],
     "correct_index": 1,
     "explanation": "The grid is the retrieval half of the comparison. Every result is a cat in a "
                    "cup, not a cup made of cat.",
     "distractor_rationale": ["The credit line is on the previous slide.", None,
                              "Resolution is never raised.", "Speed is never raised."],
     "slide_citations": [56], "topic": "Compositionality and generation", "source": "visual"},
    {"question_id": "day3-principle-q09",
     "stem": "Which family does the deck pair with self-distillation?",
     "options": ["CLIP", "MAE", "DINO", "ViT"],
     "correct_index": 2,
     "explanation": "Self-distillation is listed with DINO.",
     "distractor_rationale": ["CLIP sits under multimodal learning.",
                              "MAE sits under masked modeling.", None,
                              "ViT sits under supervised learning."],
     "slide_citations": [28], "topic": "Vision encoders", "source": "prose"},
    {"question_id": "day3-principle-q10",
     "stem": "The encoder-popularity claim in this deck is carried by:",
     "options": ["A bar chart", "A bulleted list", "A table of citations", "A spoken aside only"],
     "correct_index": 0,
     "explanation": "The families are listed in text, but the ranking exists only as bar heights.",
     "distractor_rationale": [None, "The list gives families, not their ranking.",
                              "There is no citation table.",
                              "The claim is on the slide, inside the figure."],
     "slide_citations": [28, 48], "topic": "Vision encoders", "source": "visual"},
]

STAGES = [
    ("Render", "66 pages to images at 150 DPI"),
    ("Page read, image path", "66 slides, concurrent"),
    ("Page read, text path", "66 slides, baseline"),
    ("Outline", "group slides into topics"),
    ("Research", "look up named-only concepts"),
    ("Review", "write the lesson review"),
    ("Quiz", "write ten questions"),
]

RESEARCH_LOOKUPS = [
    ("Masked modeling (MAE)", 28, "cache hit"),
    ("Self-distillation (DINO)", 28, "web search"),
    ("Reconstruction", 10, "web search"),
    ("Embodied agent", 61, "cache hit"),
]

# Slides worth jumping to on camera.
HIGHLIGHTS = [1, 10, 28, 33, 48, 55, 56, 61]
