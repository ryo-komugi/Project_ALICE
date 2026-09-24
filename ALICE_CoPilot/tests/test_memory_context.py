def test_build_memory_context_prefers_latest_memory_after_supersedes(
    memory_environment,
):
    """
    A superseded Memory must not be preferred over its replacement
    when building context.
    """

    from memory.long_term import create_memory, create_relation
    from memory.memory_context import build_memory_context

    old_memory = create_memory(
        memory_type="decision",
        title="方式A",
        content="方式Aを採用する。",
    )

    new_memory = create_memory(
        memory_type="decision",
        title="方式B",
        content="方式Bへ変更する。",
    )

    create_relation(
        from_memory_id=new_memory.stem,
        relation="supersedes",
        to_memory_id=old_memory.stem,
    )

    context = build_memory_context(
        memories=[
            {
                "id": old_memory.stem,
                "path": str(old_memory),
                "content": old_memory.read_text(encoding="utf-8"),
                "score": 10,
            }
        ],
        query="方式",
    )

    primary_ids = [
        memory["id"]
        for memory in context["primary"]
    ]

    superseded_ids = [
        memory["id"]
        for memory in context["superseded"]
    ]

    assert new_memory.stem in primary_ids
    assert old_memory.stem in superseded_ids



def test_build_memory_context_resolves_superseded_memory_to_latest(
    memory_environment,
):
    """
    When the search result contains only an old Memory,
    build_memory_context() must resolve the latest Memory
    through the supersedes relation.
    """

    from memory.long_term import (
        create_memory,
        create_relation,
    )
    from memory.memory_context import build_memory_context

    old_memory = create_memory(
        memory_type="decision",
        title="方式A",
        content="方式Aを採用する。",
    )

    new_memory = create_memory(
        memory_type="decision",
        title="方式B",
        content="方式Bへ変更する。",
    )

    create_relation(
        from_memory_id=new_memory.stem,
        relation="supersedes",
        to_memory_id=old_memory.stem,
    )

    # Search result intentionally contains only the old Memory.
    memories = [
        {
            "id": old_memory.stem,
            "path": str(old_memory),
            "content": old_memory.read_text(encoding="utf-8"),
            "score": 10,
        }
    ]

    context = build_memory_context(memories)

    primary_ids = [
        memory["id"]
        for memory in context["primary"]
    ]

    superseded_ids = [
        memory["id"]
        for memory in context["superseded"]
    ]

    assert new_memory.stem in primary_ids
    assert old_memory.stem in superseded_ids

    assert old_memory.stem not in primary_ids


def test_build_memory_context_resolves_full_supersedes_history(
    memory_environment,
):
    """
    build_memory_context() must resolve a complete supersedes chain.

    A <- B <- C

    When only A is provided as the search result:
        C must become Primary.
        B and A must be preserved as Superseded history.
    """

    from memory.long_term import (
        create_memory,
        create_relation,
    )
    from memory.memory_context import build_memory_context

    memory_a = create_memory(
        memory_type="decision",
        title="方式A",
        content="方式Aを採用する。",
    )

    memory_b = create_memory(
        memory_type="decision",
        title="方式B",
        content="方式Bへ変更する。",
    )

    memory_c = create_memory(
        memory_type="decision",
        title="方式C",
        content="方式Cへ変更する。",
    )

    create_relation(
        from_memory_id=memory_b.stem,
        relation="supersedes",
        to_memory_id=memory_a.stem,
    )

    create_relation(
        from_memory_id=memory_c.stem,
        relation="supersedes",
        to_memory_id=memory_b.stem,
    )

    memories = [
        {
            "id": memory_a.stem,
            "path": str(memory_a),
            "content": memory_a.read_text(encoding="utf-8"),
            "score": 10,
        }
    ]

    context = build_memory_context(memories)

    primary_ids = [
        memory["id"]
        for memory in context["primary"]
    ]

    superseded_ids = [
        memory["id"]
        for memory in context["superseded"]
    ]

    assert primary_ids == [memory_c.stem]

    assert memory_b.stem in superseded_ids
    assert memory_a.stem in superseded_ids

    assert memory_b.stem not in primary_ids
    assert memory_a.stem not in primary_ids


def test_build_memory_context_preserves_related_memory_as_related(
    memory_environment,
):
    """
    A related Memory must remain in the Related category and must
    not become Primary or Superseded.
    """

    from memory.long_term import (
        create_memory,
        create_relation,
    )
    from memory.memory_context import build_memory_context

    primary_memory = create_memory(
        memory_type="decision",
        title="方式A",
        content="方式Aを採用する。",
    )

    related_memory = create_memory(
        memory_type="project",
        title="方式Aの検討記録",
        content="方式Aについて検討した記録。",
    )

    create_relation(
        from_memory_id=primary_memory.stem,
        relation="related",
        to_memory_id=related_memory.stem,
    )

    memories = [
        {
            "id": primary_memory.stem,
            "path": str(primary_memory),
            "content": primary_memory.read_text(encoding="utf-8"),
            "score": 10,
        }
    ]

    context = build_memory_context(memories)

    primary_ids = [
        memory["id"]
        for memory in context["primary"]
    ]

    related_ids = [
        memory["id"]
        for memory in context["related"]
    ]

    superseded_ids = [
        memory["id"]
        for memory in context["superseded"]
    ]

    assert primary_memory.stem in primary_ids
    assert related_memory.stem in related_ids

    assert related_memory.stem not in primary_ids
    assert related_memory.stem not in superseded_ids


def test_build_memory_context_preserves_conflicting_memory_as_conflicting(
    memory_environment,
):
    """
    A conflicting Memory must remain in the Conflicting category
    and must not be treated as Superseded.
    """

    from memory.long_term import (
        create_memory,
        create_relation,
    )
    from memory.memory_context import build_memory_context

    primary_memory = create_memory(
        memory_type="decision",
        title="方式A",
        content="方式Aを採用する。",
    )

    conflicting_memory = create_memory(
        memory_type="decision",
        title="方式Aの別案",
        content="方式Aではなく方式Bを採用する。",
    )

    create_relation(
        from_memory_id=primary_memory.stem,
        relation="conflicts",
        to_memory_id=conflicting_memory.stem,
    )

    memories = [
        {
            "id": primary_memory.stem,
            "path": str(primary_memory),
            "content": primary_memory.read_text(encoding="utf-8"),
            "score": 10,
        }
    ]

    context = build_memory_context(memories)

    primary_ids = [
        memory["id"]
        for memory in context["primary"]
    ]

    conflicting_ids = [
        memory["id"]
        for memory in context["conflicting"]
    ]

    superseded_ids = [
        memory["id"]
        for memory in context["superseded"]
    ]

    # The newer conflicting Memory becomes Primary.
    assert conflicting_memory.stem in primary_ids

    # The older Memory is preserved as Conflicting.
    assert primary_memory.stem in conflicting_ids

    # Conflicts must never be treated as Superseded.
    assert primary_memory.stem not in superseded_ids
    assert conflicting_memory.stem not in superseded_ids


def test_build_memory_context_filters_related_memory_by_query_subject(
    memory_environment,
):
    """
    Related Memories that do not match the query subject must not
    be included in the Memory Context.
    """

    from memory.long_term import (
        create_memory,
        create_relation,
    )
    from memory.memory_context import build_memory_context

    primary_memory = create_memory(
        memory_type="decision",
        title="M3-4-4 の決定",
        content="M3-4-4 に関する決定事項です。",
    )

    related_memory = create_memory(
        memory_type="decision",
        title="M3-4-5 の関連Memory",
        content="M3-4-5 に関する関連情報です。",
    )

    create_relation(
        from_memory_id=primary_memory.stem,
        relation="related",
        to_memory_id=related_memory.stem,
    )

    memories = [
        {
            "id": primary_memory.stem,
            "path": str(primary_memory),
            "content": primary_memory.read_text(encoding="utf-8"),
            "score": 10,
        }
    ]

    context = build_memory_context(
        memories,
        query="M3-4-4 に関する情報を確認する。",
    )

    primary_ids = [
        memory["id"]
        for memory in context["primary"]
    ]

    related_ids = [
        memory["id"]
        for memory in context["related"]
    ]

    assert primary_memory.stem in primary_ids
    assert related_memory.stem not in related_ids


def test_build_memory_context_keeps_related_memory_with_matching_query_subject(
    memory_environment,
):
    """
    A Related Memory that matches the query subject must remain
    in the Related category.
    """

    from memory.long_term import (
        create_memory,
        create_relation,
    )
    from memory.memory_context import build_memory_context

    primary_memory = create_memory(
        memory_type="decision",
        title="M3-4-4 の決定",
        content="M3-4-4 に関する決定事項です。",
    )

    related_memory = create_memory(
        memory_type="decision",
        title="M3-4-4 の関連Memory",
        content="M3-4-4 に関する関連情報です。",
    )

    create_relation(
        from_memory_id=primary_memory.stem,
        relation="related",
        to_memory_id=related_memory.stem,
    )

    memories = [
        {
            "id": primary_memory.stem,
            "path": str(primary_memory),
            "content": primary_memory.read_text(encoding="utf-8"),
            "score": 10,
        }
    ]

    context = build_memory_context(
        memories,
        query="M3-4-4 に関する情報を確認する。",
    )

    primary_ids = [
        memory["id"]
        for memory in context["primary"]
    ]

    related_ids = [
        memory["id"]
        for memory in context["related"]
    ]

    assert primary_memory.stem in primary_ids
    assert related_memory.stem in related_ids

    superseded_ids = [
        memory["id"]
        for memory in context["superseded"]
    ]

    assert primary_memory.stem in primary_ids
    assert related_memory.stem in related_ids

    assert related_memory.stem not in superseded_ids


def test_format_memory_context_includes_supersedes_direction(
    memory_environment,
):
    """
    Superseded Memory formatting must explicitly show the
    supersedes relation direction.
    """

    from memory.long_term import (
        create_memory,
        create_relation,
    )
    from memory.memory_context import format_memory_context

    old_memory = create_memory(
        memory_type="decision",
        title="方式A",
        content="方式Aを採用する。",
    )

    new_memory = create_memory(
        memory_type="decision",
        title="方式B",
        content="方式Bへ変更する。",
    )

    create_relation(
        from_memory_id=new_memory.stem,
        relation="supersedes",
        to_memory_id=old_memory.stem,
    )

    context = {
        "primary": [
            {
                "id": new_memory.stem,
                "path": str(new_memory),
                "content": new_memory.read_text(encoding="utf-8"),
            }
        ],
        "related": [],
        "superseded": [
            {
                "id": old_memory.stem,
                "path": str(old_memory),
                "content": old_memory.read_text(encoding="utf-8"),
            }
        ],
        "superseding": [],
        "conflicting": [],
    }

    formatted = format_memory_context(context)

    assert "【Primary Memory】" in formatted
    assert "【Superseded Memory】" in formatted

    assert (
        f"{new_memory.stem} --supersedes--> {old_memory.stem}"
        in formatted
    )


def test_format_memory_context_includes_conflicts_direction(
    memory_environment,
):
    """
    Conflicting Memory formatting must explicitly show the
    conflicts relation direction.
    """

    from memory.long_term import (
        create_memory,
        create_relation,
    )
    from memory.memory_context import format_memory_context

    memory_a = create_memory(
        memory_type="decision",
        title="方式A",
        content="方式Aを採用する。",
    )

    memory_b = create_memory(
        memory_type="decision",
        title="方式B",
        content="方式Bを採用する。",
    )

    create_relation(
        from_memory_id=memory_a.stem,
        relation="conflicts",
        to_memory_id=memory_b.stem,
    )

    context = {
        "primary": [
            {
                "id": memory_a.stem,
                "path": str(memory_a),
                "content": memory_a.read_text(encoding="utf-8"),
            }
        ],
        "related": [],
        "superseded": [],
        "superseding": [],
        "conflicting": [
            {
                "id": memory_b.stem,
                "path": str(memory_b),
                "content": memory_b.read_text(encoding="utf-8"),
            }
        ],
    }

    formatted = format_memory_context(context)

    assert "【Primary Memory】" in formatted
    assert "【Conflicting Memory】" in formatted

    assert (
        f"{memory_a.stem} --conflicts--> {memory_b.stem}"
        in formatted
    )


def test_format_memory_context_includes_related_relation(
    memory_environment,
):
    """
    Related Memory formatting must explicitly identify the
    relation as related.
    """

    from memory.long_term import create_memory
    from memory.memory_context import format_memory_context

    primary_memory = create_memory(
        memory_type="decision",
        title="方式A",
        content="方式Aを採用する。",
    )

    related_memory = create_memory(
        memory_type="project",
        title="方式Aの検討記録",
        content="方式Aについて検討した記録。",
    )

    context = {
        "primary": [
            {
                "id": primary_memory.stem,
                "path": str(primary_memory),
                "content": primary_memory.read_text(encoding="utf-8"),
            }
        ],
        "related": [
            {
                "id": related_memory.stem,
                "path": str(related_memory),
                "content": related_memory.read_text(encoding="utf-8"),
            }
        ],
        "superseded": [],
        "superseding": [],
        "conflicting": [],
    }

    formatted = format_memory_context(context)

    assert "【Primary Memory】" in formatted
    assert "【Related Memory】" in formatted

    assert f"ID: {related_memory.stem}" in formatted
    assert "Relation: related" in formatted
    assert "方式Aについて検討した記録。" in formatted