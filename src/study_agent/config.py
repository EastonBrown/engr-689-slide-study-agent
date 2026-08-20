"""Every knob the pipeline reads. Spec-level unless a comment says otherwise.

Nothing here is discovered at import time and nothing depends on the machine.
Absolute paths live in `paths.py`; this file holds numbers and strings only.
"""

from __future__ import annotations

# --- Identity written into every artifact -----------------------------------

SCHEMA_VERSION = 1

# One string covering every prompt in `prompts/`, written into manifest.json.
# Bumping it is a manual act.
PROMPT_VERSION = "2026-08-20.1"

# --- Model, locked by ADR 0001 ----------------------------------------------

MODEL_ID = "claude-opus-5"

# Effort per stage. ADR 0001 fixes low for the reader and high for the outline,
# review writer, and quiz generator. Research runs at the model default.
EFFORT_PAGE_READER = "low"
EFFORT_OUTLINE = "high"
EFFORT_RESEARCH = None
EFFORT_REVIEW = "high"
EFFORT_QUIZ = "high"

# Output ceilings. A page note is small; a review over 12 topics is not.
MAX_TOKENS_PAGE_READER = 4_000
MAX_TOKENS_OUTLINE = 16_000
MAX_TOKENS_RESEARCH = 4_000
MAX_TOKENS_REVIEW = 32_000
MAX_TOKENS_QUIZ = 16_000

# Two attempts on a transport error or a schema violation, then the stage's own
# failure channel. This counts total attempts, not retries after the first.
LLM_ATTEMPTS = 2

# ADR 0001 requires one image per request with client-side concurrency; the
# width is spec-level.
READER_CONCURRENCY = 8

# --- Render, ADR 0001 pins the DPI ------------------------------------------

RENDER_DPI = 150

# Clamp on the rendered long edge, applied after rendering so a deck with pages
# larger than the course decks' 960x540 does not silently cost more per page.
#
# The high-resolution tier limit ADR 0001 chose claude-opus-5 for. An earlier
# draft of docs/spec.md named 1568, which is the standard tier and would have
# downscaled every course-deck page; see amendment 5 in docs/spec.md. Course
# decks render at 2000x1125 and pass through untouched.
MAX_LONG_EDGE_PX = 2576

# --- Preflight --------------------------------------------------------------

# A page counts as text-native when extraction yields at least this many chars.
TEXT_NATIVE_MIN_CHARS = 40
# Below this fraction of text-native pages the deck is marked image-only.
TEXT_NATIVE_MIN_FRACTION = 0.5
# Covered slide count above which topic_cap_exceeded is expected.
LONG_DECK_SLIDES = 120

# --- Build-up frame detection -----------------------------------------------

BUILDUP_DETECTION_ENABLED = True
# Both pages in a pair must carry at least this much extracted text.
BUILDUP_MIN_CHARS = 20

# --- Outline, ADR 0003 and ADR 0007 -----------------------------------------

TOPIC_CAP = 12
CANDIDATE_CAP = 30

# --- Research, ADR 0002 and ADR 0001 ----------------------------------------

RESEARCH_LOOKUP_CAP = 15  # per path per deck
WEB_SEARCH_TOOL_TYPE = "web_search_20260209"
WEB_SEARCH_MAX_USES = 4  # per request

# --- Quiz, ADR 0005 ---------------------------------------------------------

QUIZ_QUESTIONS = 10
MAX_QUESTIONS_PER_TOPIC = 3
# One question is reserved for a bridged fact when any exist.
BRIDGED_FACT_QUESTIONS = 1
# A short quiz is regenerated once for the shortfall, then shipped short.
QUIZ_REGENERATION_ATTEMPTS = 1

# --- Memory, ADR 0005 -------------------------------------------------------

# Below this many sightings a topic reports insufficient evidence, not a score.
MIN_SIGHTINGS_FOR_PERFORMANCE = 3
RETAKE_WEAK_TOPICS = 3
RETAKE_QUESTIONS_PER_WEAK_TOPIC = 2

# --- Cost accounting, ADR 0001's published rates -----------------------------

USD_PER_MTOK_INPUT = 5.00
USD_PER_MTOK_OUTPUT = 25.00
USD_PER_1K_WEB_SEARCHES = 10.00

# --- Replay -----------------------------------------------------------------

# Seconds between log lines when replaying a run for the camera.
REPLAY_LINE_DELAY_S = 0.05
