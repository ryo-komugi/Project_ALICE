import pytest


@pytest.mark.integration
def test_ask_memory_with_real_ollama_uses_saved_memory(
    memory_environment,
):
    """
    Verify that ask_memory() performs the complete Memory QA flow
    using real Ollama.

    Memory
        ↓
    Search
        ↓
    Context
        ↓
    Ollama
        ↓
    Answer
    """

    from memory.long_term import create_memory
    from memory.memory_qa import ask_memory

    memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content=(
            "監査ログはJSON形式で保存する。"
            "保存期間は7年間とする。"
        ),
    )

    question = "監査ログはどの形式で保存し、保存期間は何年ですか？"

    answer = ask_memory(question)

    print("\n[REAL OLLAMA MEMORY QA RESULT]")
    print(answer)

    assert isinstance(answer, str)
    assert answer.strip()

    assert "JSON" in answer
    assert "7" in answer


@pytest.mark.integration
def test_ask_memory_with_real_ollama_prefers_latest_superseding_memory(
    memory_environment,
):
    """
    Verify that Memory QA uses the latest Memory after supersedes.
    """

    from memory.long_term import create_memory, create_relation
    from memory.memory_qa import ask_memory

    old_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content="監査ログはCSV形式で保存する。",
    )

    new_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式の更新",
        content="監査ログはJSON形式で保存する。",
    )

    create_relation(
        from_memory_id=new_memory.stem,
        relation="supersedes",
        to_memory_id=old_memory.stem,
    )

    question = "監査ログは現在どの形式で保存しますか？"

    answer = ask_memory(question)

    print("\n[REAL OLLAMA MEMORY QA SUPERSEDES RESULT]")
    print(answer)

    assert isinstance(answer, str)
    assert answer.strip()

    assert "JSON" in answer
    assert "CSV" not in answer


@pytest.mark.integration
def test_ask_memory_with_real_ollama_preserves_conflicting_memories(
    memory_environment,
):
    """
    Verify that Memory QA preserves conflicting Memories
    as conflicting information rather than treating one as superseded.
    """

    from memory.long_term import create_memory, create_relation
    from memory.memory_qa import ask_memory

    csv_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content="監査ログはCSV形式で保存する。",
    )

    json_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式の別案",
        content="監査ログはJSON形式で保存する。",
    )

    create_relation(
        from_memory_id=csv_memory.stem,
        relation="conflicts",
        to_memory_id=json_memory.stem,
    )

    question = (
        "監査ログの保存形式について、現在のMemoryには"
        "どのような情報がありますか？"
    )

    answer = ask_memory(question)

    print("\n[REAL OLLAMA MEMORY QA CONFLICT RESULT]")
    print(answer)

    assert isinstance(answer, str)
    assert answer.strip()

    # Conflictとして両方の情報が回答に現れることを確認する。
    assert "CSV" in answer
    assert "JSON" in answer


@pytest.mark.integration
def test_ask_memory_with_real_ollama_uses_related_memory(
    memory_environment,
):
    """
    Verify that Memory QA can use a Related Memory
    when answering a question.
    """

    from memory.long_term import create_memory, create_relation
    from memory.memory_qa import ask_memory

    primary_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content="監査ログはJSON形式で保存する。",
    )

    related_memory = create_memory(
        memory_type="project",
        title="監査ログバックアップ運用",
        content="監査ログのバックアップは毎日午前3時に実施する。",
    )

    create_relation(
        from_memory_id=primary_memory.stem,
        relation="related",
        to_memory_id=related_memory.stem,
    )

    question = (
        "監査ログについて、保存形式と"
        "バックアップの実施時刻を教えてください。"
    )

    answer = ask_memory(question)

    print("\n[REAL OLLAMA MEMORY QA RELATED RESULT]")
    print(answer)

    assert isinstance(answer, str)
    assert answer.strip()

    assert "JSON" in answer
    assert "3時" in answer or "午前3時" in answer



@pytest.mark.integration
def test_ask_memory_with_real_ollama_returns_not_found_without_matching_memory(
    memory_environment,
):
    """
    Verify that Memory QA does not fabricate an answer when
    no relevant Memory exists.
    """

    from memory.long_term import create_memory
    from memory.memory_qa import ask_memory

    create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content="監査ログはJSON形式で保存する。",
    )

    question = "宇宙船の燃料補給方式について教えてください。"

    answer = ask_memory(question)

    print("\n[REAL OLLAMA MEMORY QA NOT FOUND RESULT]")
    print(answer)

    assert isinstance(answer, str)
    assert answer.strip()

    assert answer == (
        "長期記憶から関連する情報を見つけられませんでした。"
    )