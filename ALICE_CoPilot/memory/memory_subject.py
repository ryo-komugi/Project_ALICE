import re


def extract_memory_subject(text: str) -> set[str]:
    """
    Extract explicit Memory subject identifiers.

    Supported examples:
        M3-4-4
        M3-4-5
        M3-4-3-1
        TEST_CHAIN_0813_V2
        CONFLICT_TEST_0813_V5

    Subject extraction is intentionally conservative.
    Only explicit identifier-like tokens are extracted.
    """

    subjects = set()

    # M3-style identifiers.
    #
    # Do not use \b because the identifiers are commonly
    # adjacent to Japanese characters.
    subjects.update(
        re.findall(
            r"(?<![A-Za-z0-9_-])M\d+(?:-\d+)+(?![A-Za-z0-9_-])",
            text,
        )
    )

    # TEST / CONFLICT_TEST style identifiers.
    subjects.update(
        re.findall(
            r"(?<![A-Za-z0-9_-])(?:TEST|CONFLICT_TEST)_[A-Z0-9]+(?:_[A-Z0-9]+)*(?![A-Za-z0-9_-])",
            text,
        )
    )

    return subjects


def filter_memories_by_subject(title: str, content: str, candidates: list[dict]) -> list[dict]:
    """
    Filter Memory candidates by explicit subject identifiers.

    If the new/query Memory explicitly identifies a subject,
    candidates belonging to different subjects are excluded.

    Memories without an explicit subject identifier are preserved.
    """

    new_subjects = extract_memory_subject(
        f"{title}\n{content}"
    )

    if not new_subjects:
        return candidates

    filtered = []

    for candidate in candidates:
        candidate_content = candidate.get("content", "")

        candidate_title = ""
        candidate_body = candidate_content

        for line in candidate_content.splitlines():
            if line.startswith("# "):
                candidate_title = line[2:].strip()
                break

        if "## Related" in candidate_body:
            candidate_body = candidate_body.split("## Related", 1)[0]

        candidate_subjects = extract_memory_subject(
            f"{candidate_title}\n{candidate_body}"
        )

        if not candidate_subjects:
            filtered.append(candidate)
            continue

        if new_subjects & candidate_subjects:
            filtered.append(candidate)

    return filtered