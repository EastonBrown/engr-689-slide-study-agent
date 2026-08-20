"""Prompts for the outline stage."""

GROUP_NOTES = (
    "Group these compacted slide notes into deck-level topics. Reuse an existing "
    "subject topic name verbatim when it fits; otherwise declare a new topic and "
    "give a one-line created_reason. Only content slides may appear in topics."
)

CONFIRM_BRIDGES = (
    "Confirm or reject only these code-proposed bridge candidates. You may "
    "compose a joined fact from a candidate, but you may not introduce a new "
    "slide pair or candidate."
)

REPAIR_GROUPING = (
    "Repair this topic grouping by addressing the listed contract violations. "
    "Keep topic names tied to the supplied existing topic list or newly declared "
    "topics, and do not assign skipped or superseded slides to a topic."
)
