"""Where everything lives on disk, and the small IO helpers around it.

ADR 0004 fixes the layout. This module is the only place that knows it, so a
stage never joins a path by hand. Nothing here is absolute in the source: every
path descends from a repo root discovered by walking up from this file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TIMESTAMP_FORMAT = "%Y-%m-%dT%H-%M-%SZ"

_SEPARATORS = re.compile(r"[^a-z0-9]+")


def repo_root() -> Path:
    """The directory holding `docs/` and `src/`, found by walking up."""

    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "docs").is_dir() and (candidate / "src").is_dir():
            return candidate
    # Installed rather than checked out: fall back to the working directory.
    return Path.cwd()


def slugify(text: str) -> str:
    """A lowercase hyphenated slug. Never empty.

    `Day3 Principle.pdf` becomes `day3-principle`, which is the slug the eval
    labels and every ADR already name.
    """

    lowered = text.strip().lower()
    return _SEPARATORS.sub("-", lowered).strip("-") or "untitled"


def deck_slug(filename: str, sha256: str, existing: dict[str, str]) -> str:
    """The slug for a deck, disambiguated by content hash when it has to be.

    `existing` maps a slug already used in this subject to the sha256 of the
    deck that used it. A different PDF that slugifies alike gets the first
    eight characters of its own hash appended, rather than overwriting the
    other deck's run directory.
    """

    base = slugify(Path(filename).stem)
    claimed = existing.get(base)
    if claimed is None or claimed == sha256:
        return base
    return f"{base}-{sha256[:8]}"


def utc_timestamp(moment: datetime | None = None) -> str:
    """A filename-safe, sortable UTC stamp. This is a run's identity on disk."""

    moment = moment or datetime.now(timezone.utc)
    return moment.strftime(TIMESTAMP_FORMAT)


def new_attempt_id() -> str:
    """A UTC timestamp plus a short random suffix, per ADR 0005."""

    return f"{utc_timestamp()}-{os.urandom(3).hex()}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_query(query: str) -> str:
    """The research cache key's preimage.

    Lowercase, trim, collapse internal whitespace, strip trailing punctuation.
    Nothing cleverer: ADR 0003 already rejected string normalization as a way
    to merge things that mean the same, and this is a cache key, not a merge.
    """

    collapsed = " ".join(query.lower().split())
    return collapsed.rstrip(".,;:!?-").strip()


# --- Files inside one run ---------------------------------------------------


def page_render_png(run_dir: Path, slide_number: int) -> Path:
    return run_dir / "pages-render" / f"{slide_number:04d}.png"


def page_render_txt(run_dir: Path, slide_number: int) -> Path:
    return run_dir / "pages-render" / f"{slide_number:04d}.txt"


def notes_dir(run_dir: Path, path_kind: str) -> Path:
    return run_dir / f"pages-{path_kind}"


def page_note(run_dir: Path, path_kind: str, slide_number: int) -> Path:
    return notes_dir(run_dir, path_kind) / f"{slide_number:04d}.json"


def outline_file(run_dir: Path, path_kind: str) -> Path:
    return run_dir / f"outline-{path_kind}.json"


def review_file(run_dir: Path, path_kind: str) -> Path:
    return run_dir / f"review-{path_kind}.md"


def manifest_file(run_dir: Path) -> Path:
    return run_dir / "manifest.json"


def quiz_file(run_dir: Path) -> Path:
    return run_dir / "quiz.json"


def run_research_dir(run_dir: Path) -> Path:
    return run_dir / "research"


# --- The trees --------------------------------------------------------------


@dataclass(frozen=True)
class Layout:
    """The four trees ADR 0004 names, rooted anywhere (tests root them in tmp)."""

    root: Path | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", Path(self.root) if self.root else repo_root())

    # runs/
    def runs_dir(self) -> Path:
        return self.root / "runs"

    def deck_dir(self, subject_slug: str, deck_slug_: str) -> Path:
        return self.runs_dir() / subject_slug / deck_slug_

    def run_dir(self, subject_slug: str, deck_slug_: str, run_timestamp: str) -> Path:
        return self.deck_dir(subject_slug, deck_slug_) / run_timestamp

    def latest_file(self, subject_slug: str, deck_slug_: str) -> Path:
        return self.deck_dir(subject_slug, deck_slug_) / "latest"

    def write_latest(self, subject_slug: str, deck_slug_: str, run_timestamp: str) -> None:
        target = self.latest_file(subject_slug, deck_slug_)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(run_timestamp + "\n", encoding="utf-8")

    def read_latest(self, subject_slug: str, deck_slug_: str) -> str | None:
        target = self.latest_file(subject_slug, deck_slug_)
        if not target.is_file():
            return None
        return target.read_text(encoding="utf-8").strip() or None

    def latest_run_dir(self, subject_slug: str, deck_slug_: str) -> Path | None:
        stamp = self.read_latest(subject_slug, deck_slug_)
        if stamp is None:
            return None
        candidate = self.run_dir(subject_slug, deck_slug_, stamp)
        return candidate if candidate.is_dir() else None

    def deck_slugs_with_hashes(self, subject_slug: str) -> dict[str, str]:
        """Every deck slug already used in this subject, mapped to its sha256.

        Read from each deck's newest manifest, since that is where the hash is
        recorded. A deck directory with no readable manifest is skipped rather
        than treated as a collision.
        """

        found: dict[str, str] = {}
        subject_dir = self.runs_dir() / subject_slug
        if not subject_dir.is_dir():
            return found
        for deck_dir in sorted(p for p in subject_dir.iterdir() if p.is_dir()):
            for run_dir in sorted(
                (p for p in deck_dir.iterdir() if p.is_dir()), reverse=True
            ):
                manifest = read_json(manifest_file(run_dir))
                if manifest and manifest.get("deck_sha256"):
                    found[deck_dir.name] = manifest["deck_sha256"]
                    break
        return found

    # memory/
    def memory_dir(self) -> Path:
        return self.root / "memory"

    def subjects_file(self) -> Path:
        return self.memory_dir() / "subjects.json"

    def subject_dir(self, subject_slug: str) -> Path:
        return self.memory_dir() / subject_slug

    def profile_file(self, subject_slug: str) -> Path:
        return self.subject_dir(subject_slug) / "profile.json"

    def contributions_dir(self, subject_slug: str) -> Path:
        return self.subject_dir(subject_slug) / "contributions"

    def contribution_file(self, subject_slug: str, deck_slug_: str) -> Path:
        return self.contributions_dir(subject_slug) / f"{deck_slug_}.json"

    def attempts_dir(self, subject_slug: str) -> Path:
        return self.subject_dir(subject_slug) / "attempts"

    def attempt_file(self, subject_slug: str, attempt_id: str) -> Path:
        return self.attempts_dir(subject_slug) / f"{attempt_id}.json"

    def retakes_dir(self, subject_slug: str) -> Path:
        return self.subject_dir(subject_slug) / "retakes"

    def retake_file(self, subject_slug: str, retake_id: str) -> Path:
        return self.retakes_dir(subject_slug) / f"{retake_id}.json"

    # cache/ and eval/
    def research_cache_dir(self) -> Path:
        return self.root / "cache" / "research"

    def research_cache_file(self, query: str) -> Path:
        key = sha256_text(normalize_query(query))
        return self.research_cache_dir() / f"{key}.json"

    def figure_only_facts_file(self) -> Path:
        return self.root / "eval" / "figure-only-facts.json"

    def golden_run_dir(self) -> Path:
        return self.root / "examples" / "golden"


# --- JSON, written the same way everywhere ----------------------------------


def write_json(target: Path, payload: Any) -> None:
    """Write one JSON file, creating parents. Replaces, never appends."""

    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    target.write_text(text + "\n", encoding="utf-8")


def write_model(target: Path, model: Any) -> None:
    """Write a Pydantic model as JSON, with enums flattened to their values."""

    write_json(target, json.loads(model.model_dump_json()))


def read_json(target: Path) -> Any | None:
    """Parse one JSON file. Missing or unparseable reads as None."""

    if not target.is_file():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def write_text(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
