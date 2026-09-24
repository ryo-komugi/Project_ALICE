from memory.memory_subject import filter_memories_by_subject


def test_filter_memories_by_subject_keeps_matching_subject():
    """
    When the new Memory explicitly identifies a subject,
    candidates with the same subject are retained while
    candidates with a different subject are excluded.
    """

    candidates = [
        {
            "id": "matching-memory",
            "path": "",
            "content": (
                "# 同一SubjectのMemory\n\n"
                "M3-4-4 に関する決定事項です。\n"
            ),
            "score": 10,
        },
        {
            "id": "different-memory",
            "path": "",
            "content": (
                "# 別SubjectのMemory\n\n"
                "M3-4-5 に関する決定事項です。\n"
            ),
            "score": 9,
        },
    ]

    result = filter_memories_by_subject(
        title="M3-4-4 の新しい決定",
        content="M3-4-4 に関する追加の決定事項です。",
        candidates=candidates,
    )

    assert [item["id"] for item in result] == [
        "matching-memory"
    ]


def test_filter_memories_by_subject_keeps_candidate_without_subject():
    """
    A candidate without an explicit subject must remain eligible
    even when the new Memory has an explicit subject.
    """

    candidates = [
        {
            "id": "matching-memory",
            "path": "",
            "content": (
                "# 同一SubjectのMemory\n\n"
                "M3-4-4 に関する決定事項です。\n"
            ),
            "score": 10,
        },
        {
            "id": "subjectless-memory",
            "path": "",
            "content": (
                "# SubjectなしのMemory\n\n"
                "一般的なProject_ALICEの設計方針について記録しています。\n"
            ),
            "score": 9,
        },
    ]

    result = filter_memories_by_subject(
        title="M3-4-4 の新しい決定",
        content="M3-4-4 に関する追加の決定事項です。",
        candidates=candidates,
    )

    result_ids = [item["id"] for item in result]

    assert result_ids == [
        "matching-memory",
        "subjectless-memory",
    ]


def test_filter_memories_by_subject_keeps_all_when_new_memory_has_no_subject():
    """
    When the new Memory has no explicit subject,
    Subject filtering must not remove any candidates.
    """

    candidates = [
        {
            "id": "subject-a",
            "path": "",
            "content": (
                "# Subject A\n\n"
                "M3-4-4 に関するMemoryです。\n"
            ),
            "score": 10,
        },
        {
            "id": "subject-b",
            "path": "",
            "content": (
                "# Subject B\n\n"
                "M3-4-5 に関するMemoryです。\n"
            ),
            "score": 9,
        },
        {
            "id": "subjectless",
            "path": "",
            "content": (
                "# Subjectなし\n\n"
                "一般的な設計方針について記録しています。\n"
            ),
            "score": 8,
        },
    ]

    result = filter_memories_by_subject(
        title="Project_ALICE全体の追加情報",
        content="複数のSubjectにまたがる一般的な情報です。",
        candidates=candidates,
    )

    assert [item["id"] for item in result] == [
        "subject-a",
        "subject-b",
        "subjectless",
    ]


def test_filter_memories_by_subject_ignores_related_subjects():
    """
    Subject filtering must ignore Subject-like identifiers
    that appear only inside the ## Related section.
    """

    candidates = [
        {
            "id": "target-memory",
            "path": "",
            "content": (
                "# SubjectなしのMemory\n\n"
                "一般的なProject_ALICEの設計方針です。\n\n"
                "## Related\n"
                "- [[M3-4-4]]\n"
            ),
            "score": 10,
        },
        {
            "id": "different-subject",
            "path": "",
            "content": (
                "# M3-4-5 のMemory\n\n"
                "別Subjectの内容です。\n"
            ),
            "score": 9,
        },
    ]

    result = filter_memories_by_subject(
        title="M3-4-4 の新しい決定",
        content="M3-4-4 に関する追加の決定事項です。",
        candidates=candidates,
    )

    result_ids = [item["id"] for item in result]

    assert "target-memory" in result_ids
    assert "different-subject" not in result_ids


def test_filter_memories_by_subject_keeps_candidate_with_multiple_subjects():
    """
    A candidate containing multiple explicit subjects must be retained
    when at least one subject matches the new Memory.
    """

    candidates = [
        {
            "id": "multi-subject-memory",
            "path": "",
            "content": (
                "# 複数SubjectのMemory\n\n"
                "M3-4-4 と M3-4-5 の両方に関係する決定事項です。\n"
            ),
            "score": 10,
        },
        {
            "id": "different-subject-memory",
            "path": "",
            "content": (
                "# 別SubjectのMemory\n\n"
                "M3-4-6 に関する決定事項です。\n"
            ),
            "score": 9,
        },
    ]

    result = filter_memories_by_subject(
        title="M3-4-5 の新しい決定",
        content="M3-4-5 に関する追加の決定事項です。",
        candidates=candidates,
    )

    result_ids = [item["id"] for item in result]

    assert "multi-subject-memory" in result_ids
    assert "different-subject-memory" not in result_ids



def test_extract_memory_subject_detects_supported_subject_formats():
    """
    Supported explicit Subject formats must be extracted.
    """

    from memory.memory_subject import extract_memory_subject

    content = """
# テストMemory

M3-4-4 に関する決定事項です。

TEST_CHAIN_0813_V2 に関する追加情報です。
"""

    subjects = extract_memory_subject(content)

    assert subjects == {
        "M3-4-4",
        "TEST_CHAIN_0813_V2",
    }


def test_extract_memory_subject_ignores_related_section():
    """
    Subject-like identifiers inside ## Related must not be extracted.
    """

    from memory.memory_subject import extract_memory_subject

    content = """
# 通常のMemory

Project_ALICEの一般的な設計方針について記録します。

## Related

- [[M3-4-4_関連Memory]]
- [[TEST_CHAIN_0813_V2_関連Memory]]
"""

    subjects = extract_memory_subject(content)

    assert subjects == set()


def test_extract_memory_subject_returns_empty_for_unrelated_text():
    """
    Ordinary text without an explicit supported Subject identifier
    must produce no subjects.
    """

    from memory.memory_subject import extract_memory_subject

    content = """
# Project_ALICEの設計方針

ALICE_CoPilotではMemoryを長期記憶として保存する。
RelationによってMemory間の関係を管理する。
検索結果から関連するMemoryを候補として取得する。
"""

    subjects = extract_memory_subject(content)

    assert subjects == set()