from memory.memory_search import search_memories


def test_search_memories_ranks_title_match_above_body_match(
    memory_environment,
):
    """
    Title matches must receive a higher score than body-only matches.
    """

    title_match = (
        memory_environment
        / "decision"
        / "20260815_120000_000000_検索対象A.md"
    )

    body_match = (
        memory_environment
        / "decision"
        / "20260815_120001_000000_検索対象B.md"
    )

    title_match.parent.mkdir(parents=True)

    title_match.write_text(
        "# ALICE検索テスト\n\n"
        "これは検索対象Aの本文です。\n",
        encoding="utf-8",
    )

    body_match.write_text(
        "# 別のMemory\n\n"
        "このMemoryの本文にはALICE検索テストが含まれます。\n",
        encoding="utf-8",
    )

    results = search_memories(
        query="ALICE検索テスト",
        limit=10,
    )

    assert len(results) == 2

    assert results[0]["id"] == title_match.stem
    assert results[1]["id"] == body_match.stem

    assert results[0]["score"] > results[1]["score"]


def test_search_memories_ignores_related_section(
    memory_environment,
):
    """
    Content under ## Related must not affect search results.
    """

    related_only = (
        memory_environment
        / "decision"
        / "20260815_120002_000000_Relatedのみ.md"
    )

    actual_match = (
        memory_environment
        / "decision"
        / "20260815_120003_000000_実本文一致.md"
    )

    related_only.parent.mkdir(parents=True)

    related_only.write_text(
        "# Relatedのみ\n\n"
        "このMemory本文には検索語がありません。\n\n"
        "## Related\n"
        "- [[ALICE検索テスト]]\n",
        encoding="utf-8",
    )

    actual_match.write_text(
        "# 実本文一致\n\n"
        "ALICE検索テストについて記録したMemoryです。\n",
        encoding="utf-8",
    )

    results = search_memories(
        query="ALICE検索テスト",
        limit=10,
    )

    result_ids = [item["id"] for item in results]

    assert actual_match.stem in result_ids
    assert related_only.stem not in result_ids


def test_search_memories_excludes_archive(
    memory_environment,
):
    """
    Archive Memories must not appear in search results.
    """

    current_memory = (
        memory_environment
        / "decision"
        / "20260815_120004_000000_CurrentMemory.md"
    )

    archive_memory = (
        memory_environment
        / "Archive"
        / "20260815_120005_000000_HistoricalMemory.md"
    )

    current_memory.parent.mkdir(parents=True)
    archive_memory.parent.mkdir(parents=True)

    current_memory.write_text(
        "# CurrentMemory\n\n"
        "ALICE検索テストに関する現在のMemoryです。\n",
        encoding="utf-8",
    )

    archive_memory.write_text(
        "# HistoricalMemory\n\n"
        "ALICE検索テストに関する過去のMemoryです。\n",
        encoding="utf-8",
    )

    results = search_memories(
        query="ALICE検索テスト",
        limit=10,
    )

    result_ids = [item["id"] for item in results]

    assert current_memory.stem in result_ids
    assert archive_memory.stem not in result_ids


def test_search_memories_excludes_zero_score_memories(
    memory_environment,
):
    """
    Memories with no matching keywords must not appear
    in search results.
    """

    matching_memory = (
        memory_environment
        / "decision"
        / "20260815_120006_000000_一致するMemory.md"
    )

    unrelated_memory = (
        memory_environment
        / "decision"
        / "20260815_120007_000000_無関係なMemory.md"
    )

    matching_memory.parent.mkdir(parents=True)

    matching_memory.write_text(
        "# 一致するMemory\n\n"
        "ALICE検索テストについて記録したMemoryです。\n",
        encoding="utf-8",
    )

    unrelated_memory.write_text(
        "# 無関係なMemory\n\n"
        "これはまったく別の内容を記録したMemoryです。\n",
        encoding="utf-8",
    )

    results = search_memories(
        query="ALICE検索テスト",
        limit=10,
    )

    result_ids = [item["id"] for item in results]

    assert matching_memory.stem in result_ids
    assert unrelated_memory.stem not in result_ids


def test_search_memories_respects_limit(
    memory_environment,
):
    """
    Search results must not exceed the requested limit.
    """

    memory_dir = memory_environment / "decision"
    memory_dir.mkdir(parents=True)

    for index in range(5):
        path = (
            memory_dir
            / f"20260815_12000{index}_000000_"
              f"ALICE検索テスト_{index}.md"
        )

        path.write_text(
            f"# ALICE検索テスト {index}\n\n"
            "ALICE検索テストに関するMemoryです。\n",
            encoding="utf-8",
        )

    results = search_memories(
        query="ALICE検索テスト",
        limit=3,
    )

    assert len(results) == 3


def test_search_memories_sorts_equal_scores_by_id(
    memory_environment,
):
    """
    Memories with equal scores must be sorted deterministically
    by Memory ID.
    """

    memory_dir = memory_environment / "decision"
    memory_dir.mkdir(parents=True)

    memory_a = (
        memory_dir
        / "20260815_120010_000000_ALICE検索テスト_A.md"
    )

    memory_b = (
        memory_dir
        / "20260815_120009_000000_ALICE検索テスト_B.md"
    )

    memory_a.write_text(
        "# ALICE検索テスト\n\n"
        "同じ検索スコアになるMemoryです。\n",
        encoding="utf-8",
    )

    memory_b.write_text(
        "# ALICE検索テスト\n\n"
        "同じ検索スコアになるMemoryです。\n",
        encoding="utf-8",
    )

    results = search_memories(
        query="ALICE検索テスト",
        limit=10,
    )

    assert len(results) == 2

    result_ids = [item["id"] for item in results]

    assert result_ids == sorted(result_ids)


def test_search_memories_finds_japanese_keywords(
    memory_environment,
):
    """
    Japanese keywords must be searchable.
    """

    target = (
        memory_environment
        / "decision"
        / "20260815_120011_000000_議事録方式.md"
    )

    target.parent.mkdir(parents=True)

    target.write_text(
        "# 議事録方式\n\n"
        "ALICEでは議事録をMarkdown形式で保存する。\n",
        encoding="utf-8",
    )

    results = search_memories(
        query="議事録 Markdown",
        limit=10,
    )

    result_ids = [item["id"] for item in results]

    assert target.stem in result_ids


def test_extract_keywords_katakana_variants():
    """
    Katakana keyword extraction must support:
    - Normal Katakana (e.g. ドメイン, サーバー)
    - Middle dot compounds (e.g. ゼロ・トラスト -> 'ゼロ・トラスト', 'ゼロ', 'トラスト')
    - Voiced/variant Katakana (e.g. ヴァイオリン, ヴォルテックス)
    - Half-width Katakana via NFKC normalization (e.g. ﾃﾞｰﾀﾍﾞｰｽ -> データベース)
    """
    from memory.memory_search import extract_keywords

    # 1. Normal Katakana
    kw1 = extract_keywords("ドメインとサーバーの設定について")
    assert "ドメイン" in kw1
    assert "サーバー" in kw1
    assert "設定" in kw1

    # 2. Middle dot compound
    kw2 = extract_keywords("ゼロ・トラストのアーキテクチャ方針")
    assert "ゼロ・トラスト" in kw2
    assert "ゼロ" in kw2
    assert "トラスト" in kw2
    assert "アーキテクチャ" in kw2

    # 3. Half-width Katakana
    kw3 = extract_keywords("ﾃﾞｰﾀﾍﾞｰｽのバックアップ")
    assert "データベース" in kw3
    assert "バックアップ" in kw3

    # 4. Voiced / Special Katakana
    kw4 = extract_keywords("ヴォルテックスとヴァイオリン")
    assert "ヴォルテックス" in kw4
    assert "ヴァイオリン" in kw4


def test_search_memories_finds_katakana_compound_and_variants(
    memory_environment,
):
    """
    Search must successfully find memories using Katakana compound terms
    and normalized half-width Katakana.
    """
    target = (
        memory_environment
        / "decision"
        / "20260815_120012_000000_ゼロトラスト方針.md"
    )
    target.parent.mkdir(parents=True)
    target.write_text(
        "# ゼロ・トラスト移行方針\n\n"
        "Cloudflare Zero Trustを採用しゼロ・トラスト境界認証を確立する。\n",
        encoding="utf-8",
    )

    # Search with compound word
    results = search_memories(query="ゼロ・トラストについて教えて", limit=5)
    assert len(results) > 0
    assert results[0]["id"] == target.stem

    # Search with half-width katakana
    results_hw = search_memories(query="ｾﾞﾛ･ﾄﾗｽﾄ", limit=5)
    assert len(results_hw) > 0
    assert results_hw[0]["id"] == target.stem