import re
import unicodedata
import config
from memory.long_term import is_valid_memory_file


MEMORY_ROOT = config.MEMORY_ROOT
ARCHIVE_ROOT = config.ARCHIVE_ROOT


def extract_keywords(query: str) -> list[str]:
    """
    Extract simple keywords from Japanese / English queries.
    Supports standard Katakana, Katakana compounds with middle dot (・),
    voiced/semi-voiced variants (ヴ/ヷ-ヺ), and half-width Katakana via NFKC normalization.
    """
    if not query:
        return []

    # Unicode normalization (half-width Katakana -> full-width, full-width alphanumerics -> half-width)
    normalized = unicodedata.normalize("NFKC", query)

    # Katakana character range: ァ-ヶ, ヴ, ヷ-ヺ (\u30A1-\u30FA) and prolonged mark ー (\u30FC)
    katakana_char = r"[\u30A1-\u30FA\u30FC]"

    # Extract compound Katakana joined by middle dot (e.g. ゼロ・トラスト) and individual Katakana terms
    compound_katakana = re.findall(rf"{katakana_char}+(?:・{katakana_char}+)+", normalized)
    single_katakana = re.findall(rf"{katakana_char}{{2,}}", normalized)
    katakana_terms = compound_katakana + single_katakana

    clean_query = re.sub(r"[、。！？？!?,.]", " ", normalized)

    # Common Japanese particles / phrases
    clean_query = re.sub(
        r"(について|に関して|とは|って|の|は|を|が|に|へ|で|と|から|まで|や)",
        " ",
        clean_query,
    )

    english_terms = re.findall(r"[A-Za-z0-9_]+", clean_query)
    japanese_terms = re.findall(
        rf"[一-龯ぁ-ん\u30A1-\u30FA\u30FC]{{2,}}",
        clean_query,
    )

    stopwords = {
        "何",
        "何を",
        "教えて",
        "ください",
        "ですか",
        "ますか",
        "決めた",
        "決めたこと",
        "いつ",
        "どこ",
        "どう",
        "なん",
        "なった",
    }

    keywords = []

    for word in katakana_terms + english_terms + japanese_terms:
        if len(word) < 2:
            continue

        if word in stopwords:
            continue

        if word not in keywords:
            keywords.append(word)

    return keywords


def _split_memory_text(text: str) -> tuple[str, str]:
    """
    Split a Memory Markdown into title and searchable body.

    The Related section is excluded from the searchable body because
    relation links should not influence keyword search ranking.
    """

    lines = text.splitlines()

    title = ""
    body_lines = []

    for line in lines:
        if not title and line.startswith("# "):
            title = line[2:].strip()
            continue

        if line.startswith("## Related"):
            break

        body_lines.append(line)

    body = "\n".join(body_lines)

    return title, body


def _calculate_score(keywords: list[str], title: str, body: str) -> int:
    """
    Calculate search score.

    Title matches are weighted more heavily than body matches.

    Title:
        +3 per matched keyword

    Body:
        +1 per matched keyword
    """

    score = 0

    for word in keywords:
        if word in title:
            score += 3

        if word in body:
            score += 1

    return score


def search_memories(query: str, limit: int = 10) -> list[dict]:
    """
    Search long-term memory Markdown files.

    Search ranking is based on:
        - title keyword matches
        - body keyword matches

    The Related section is excluded from scoring.

    Archive memories are excluded.
    """

    query_words = extract_keywords(query)

    if not query_words:
        return []

    results = []

    for path in MEMORY_ROOT.rglob("*.md"):
        if not is_valid_memory_file(path):
            continue

        if ARCHIVE_ROOT in path.parents:
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        title, body = _split_memory_text(text)

        score = _calculate_score(keywords=query_words, title=title, body=body)

        if score == 0:
            continue

        results.append(
            {
                "id": path.stem,
                "path": str(path),
                "content": text,
                "score": score,
            }
        )

    results.sort(
        key=lambda item: (
            -item["score"],
            item["id"],
        ),
        reverse=False,
    )

    return results[:limit]
