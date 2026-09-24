def test_migrate_related_creates_relation_from_markdown(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    source_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content=(
            "# 監査ログ保存方式\n\n"
            "監査ログはJSON形式で保存する。\n\n"
            "## Related\n\n"
            "- [[PLACEHOLDER]]\n"
        ),
    )

    target_memory = create_memory(
        memory_type="project",
        title="監査ログ運用",
        content="監査ログの運用方法を定義する。",
    )

    source_text = source_memory.read_text(encoding="utf-8")

    source_memory.write_text(
        source_text.replace(
            "[[PLACEHOLDER]]",
            f"[[{target_memory.stem}]]",
        ),
        encoding="utf-8",
    )

    result = memory.cli.handle_migrate_related(None)

    assert result == 0

    relations = load_relations()

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
        and relation.get("to") == target_memory.stem
    ]

    assert len(matching) == 1


def test_migrate_related_ignores_wikilinks_outside_related_section(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    source_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content=(
            "# 監査ログ保存方式\n\n"
            "本文中の [[PLACEHOLDER_BODY]] は参照リンクだが、"
            "Relatedではない。\n\n"
            "## Related\n\n"
            "- [[PLACEHOLDER_RELATED]]\n"
        ),
    )

    body_memory = create_memory(
        memory_type="project",
        title="本文参照先",
        content="本文リンクの対象。",
    )

    related_memory = create_memory(
        memory_type="project",
        title="Related対象",
        content="Relatedリンクの対象。",
    )

    source_text = source_memory.read_text(encoding="utf-8")

    source_memory.write_text(
        source_text
        .replace(
            "[[PLACEHOLDER_BODY]]",
            f"[[{body_memory.stem}]]",
        )
        .replace(
            "[[PLACEHOLDER_RELATED]]",
            f"[[{related_memory.stem}]]",
        ),
        encoding="utf-8",
    )

    result = memory.cli.handle_migrate_related(None)

    assert result == 0

    relations = load_relations()

    related_relations = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
    ]

    assert len(related_relations) == 1

    assert related_relations[0]["to"] == related_memory.stem


def test_migrate_related_ignores_missing_memory_id(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    source_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content=(
            "# 監査ログ保存方式\n\n"
            "監査ログはJSON形式で保存する。\n\n"
            "## Related\n\n"
            "- [[存在しないMemory_ID]]\n"
        ),
    )

    result = memory.cli.handle_migrate_related(None)

    assert result == 0

    relations = load_relations()

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
    ]

    assert matching == []


def test_migrate_related_ignores_project_and_repository_links(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    source_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content=(
            "# 監査ログ保存方式\n\n"
            "## Related\n\n"
            "- [[Project_ALICE]]\n"
            "- [[ALICE_CoPilot]]\n"
        ),
    )

    result = memory.cli.handle_migrate_related(None)

    assert result == 0

    relations = load_relations()

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
    ]

    assert matching == []


def test_migrate_related_is_idempotent(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    source_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content=(
            "# 監査ログ保存方式\n\n"
            "## Related\n\n"
            "- [[PLACEHOLDER]]\n"
        ),
    )

    target_memory = create_memory(
        memory_type="project",
        title="監査ログ運用",
        content="監査ログの運用方法を定義する。",
    )

    source_text = source_memory.read_text(encoding="utf-8")

    source_memory.write_text(
        source_text.replace(
            "[[PLACEHOLDER]]",
            f"[[{target_memory.stem}]]",
        ),
        encoding="utf-8",
    )

    # 1回目
    result1 = memory.cli.handle_migrate_related(None)

    assert result1 == 0

    relations_after_first = load_relations()

    matching_after_first = [
        relation
        for relation in relations_after_first
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
        and relation.get("to") == target_memory.stem
    ]

    assert len(matching_after_first) == 1

    # 2回目
    result2 = memory.cli.handle_migrate_related(None)

    assert result2 == 0

    relations_after_second = load_relations()

    matching_after_second = [
        relation
        for relation in relations_after_second
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
        and relation.get("to") == target_memory.stem
    ]

    assert len(matching_after_second) == 1


def test_migrate_related_allows_archive_memory_as_target(
    memory_environment,
):
    import importlib
    import shutil

    import memory.cli
    import memory.long_term

    importlib.reload(memory.long_term)
    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    source_memory = create_memory(
        memory_type="decision",
        title="現行Memory",
        content=(
            "# 現行Memory\n\n"
            "## Related\n\n"
            "- [[PLACEHOLDER]]\n"
        ),
    )

    archive_memory = create_memory(
        memory_type="decision",
        title="過去Memory",
        content="過去のMemoryです。",
    )

    archive_path = memory.long_term.ARCHIVE_ROOT / archive_memory.name
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(
        str(archive_memory),
        str(archive_path),
    )

    source_text = source_memory.read_text(encoding="utf-8")
    source_memory.write_text(
        source_text.replace(
            "[[PLACEHOLDER]]",
            f"[[{archive_memory.stem}]]",
        ),
        encoding="utf-8",
    )

    result = memory.cli.handle_migrate_related(None)

    assert result == 0

    relations = load_relations()

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
        and relation.get("to") == archive_memory.stem
    ]

    assert len(matching) == 1


def test_migrate_related_ignores_archive_memory_as_source(
    memory_environment,
):
    import importlib
    import shutil

    import memory.cli
    import memory.long_term

    importlib.reload(memory.long_term)
    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    archive_memory = create_memory(
        memory_type="decision",
        title="過去Memory",
        content=(
            "# 過去Memory\n\n"
            "## Related\n\n"
            "- [[PLACEHOLDER]]\n"
        ),
    )

    target_memory = create_memory(
        memory_type="project",
        title="関連Memory",
        content="関連するMemoryです。",
    )

    archive_path = memory.long_term.ARCHIVE_ROOT / archive_memory.name
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    shutil.move(
        str(archive_memory),
        str(archive_path),
    )

    archive_text = archive_path.read_text(encoding="utf-8")

    archive_path.write_text(
        archive_text.replace(
            "[[PLACEHOLDER]]",
            f"[[{target_memory.stem}]]",
        ),
        encoding="utf-8",
    )

    result = memory.cli.handle_migrate_related(None)

    assert result == 0

    relations = load_relations()

    matching = [
        relation
        for relation in relations
        if relation.get("from") == archive_memory.stem
        and relation.get("relation") == "related"
        and relation.get("to") == target_memory.stem
    ]

    assert matching == []


def test_migrate_related_dry_run_does_not_create_relation(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    source_memory = create_memory(
        memory_type="decision",
        title="監査ログ保存方式",
        content=(
            "# 監査ログ保存方式\n\n"
            "## Related\n\n"
            "- [[PLACEHOLDER]]\n"
        ),
    )

    target_memory = create_memory(
        memory_type="project",
        title="監査ログ運用",
        content="監査ログの運用方法を定義する。",
    )

    source_text = source_memory.read_text(encoding="utf-8")

    source_memory.write_text(
        source_text.replace(
            "[[PLACEHOLDER]]",
            f"[[{target_memory.stem}]]",
        ),
        encoding="utf-8",
    )

    result = memory.cli.handle_migrate_related(
        type("Args", (), {"dry_run": True})()
    )

    assert result == 0

    relations = load_relations()

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
        and relation.get("to") == target_memory.stem
    ]

    assert matching == []


def test_migrate_related_continues_after_missing_memory_id(
    memory_environment,
):
    """
    A missing Related target must not prevent valid Relations
    from being migrated in the same source Memory.
    """
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    source_memory = create_memory(
        memory_type="decision",
        title="Related Migration Test",
        content=(
            "# Related Migration Test\n\n"
            "## Related\n\n"
            "- [[20260815_000000_000000_missing_Memory]]\n"
            "- [[PLACEHOLDER]]\n"
        ),
    )

    target_memory = create_memory(
        memory_type="project",
        title="Existing Target",
        content="存在するRelated対象です。",
    )

    source_text = source_memory.read_text(encoding="utf-8")

    source_memory.write_text(
        source_text.replace(
            "[[PLACEHOLDER]]",
            f"[[{target_memory.stem}]]",
        ),
        encoding="utf-8",
    )

    result = memory.cli.handle_migrate_related(
        type("Args", (), {"dry_run": False})()
    )

    assert result == 0

    relations = load_relations()

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
        and relation.get("to") == target_memory.stem
    ]

    assert len(matching) == 1


def test_migrate_related_does_not_duplicate_same_link_within_markdown(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    source_memory = create_memory(
        memory_type="decision",
        title="重複Relatedテスト",
        content=(
            "# 重複Relatedテスト\n\n"
            "## Related\n\n"
            "- [[PLACEHOLDER]]\n"
            "- [[PLACEHOLDER]]\n"
            "- [[PLACEHOLDER]]\n"
        ),
    )

    target_memory = create_memory(
        memory_type="project",
        title="Related対象",
        content="Related対象のMemoryです。",
    )

    source_text = source_memory.read_text(encoding="utf-8")

    source_memory.write_text(
        source_text.replace(
            "[[PLACEHOLDER]]",
            f"[[{target_memory.stem}]]",
        ),
        encoding="utf-8",
    )

    result = memory.cli.handle_migrate_related(
        type("Args", (), {"dry_run": False})()
    )

    assert result == 0

    relations = load_relations()

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
        and relation.get("to") == target_memory.stem
    ]

    assert len(matching) == 1


def test_add_creates_memory(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import find_memory_by_id

    args = type(
        "Args",
        (),
        {
            "type": "decision",
            "title": "テスト決定事項",
            "content": "これはテスト用の決定事項です。",
            "supersedes": None,
            "related": None,
            "conflicts": None,
            "json": False,
        },
    )()

    result = memory.cli.handle_add(args)

    assert result == 0

    # 作成されたMemoryを検索するため、
    # Memory Rootから新しく作成されたものを確認する。
    from memory.long_term import MEMORY_ROOT

    memories = [
        path
        for path in MEMORY_ROOT.rglob("*.md")
        if path.is_file()
    ]

    matching = []

    for path in memories:
        text = path.read_text(encoding="utf-8")

        if "テスト決定事項" in text:
            matching.append(path)

    assert len(matching) == 1

    memory_id = matching[0].stem

    loaded = find_memory_by_id(memory_id)

    assert loaded is not None
    assert loaded == matching[0]


def test_add_creates_requested_relations(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import (
        create_memory,
        load_relations,
    )

    superseded_memory = create_memory(
        memory_type="decision",
        title="旧決定",
        content="以前の決定事項です。",
    )

    related_memory = create_memory(
        memory_type="project",
        title="関連プロジェクト",
        content="関連するプロジェクトです。",
    )

    conflicting_memory = create_memory(
        memory_type="knowledge",
        title="矛盾する情報",
        content="現在の決定とは異なる情報です。",
    )

    args = type(
        "Args",
        (),
        {
            "type": "decision",
            "title": "新しい決定",
            "content": "新しい決定事項です。",
            "supersedes": [superseded_memory.stem],
            "related": [related_memory.stem],
            "conflicts": [conflicting_memory.stem],
            "json": False,
        },
    )()

    result = memory.cli.handle_add(args)

    assert result == 0

    relations = load_relations()

    created_memory_id = None

    # 新しく作られたMemoryを特定する。
    from memory.long_term import MEMORY_ROOT

    for path in MEMORY_ROOT.rglob("*.md"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            if "新しい決定事項です。" in text:
                created_memory_id = path.stem
                break

    assert created_memory_id is not None

    matching = [
        relation
        for relation in relations
        if relation.get("from") == created_memory_id
    ]

    assert {
        (
            relation.get("relation"),
            relation.get("to"),
        )
        for relation in matching
    } == {
        ("supersedes", superseded_memory.stem),
        ("related", related_memory.stem),
        ("conflicts", conflicting_memory.stem),
    }


def test_add_rejects_missing_relation_target_without_creating_memory(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import MEMORY_ROOT

    args = type(
        "Args",
        (),
        {
            "type": "decision",
            "title": "作成されてはいけないMemory",
            "content": "Relation targetが存在しないため作成されない。",
            "supersedes": ["nonexistent-memory-id"],
            "related": None,
            "conflicts": None,
            "json": False,
        },
    )()

    result = memory.cli.handle_add(args)

    assert result == 1

    matching = [
        path
        for path in MEMORY_ROOT.rglob("*.md")
        if path.is_file()
        and "作成されてはいけないMemory" in path.read_text(encoding="utf-8")
    ]

    assert matching == []


def test_add_json_outputs_created_memory_result(
    memory_environment,
    capsys,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    args = type(
        "Args",
        (),
        {
            "type": "decision",
            "title": "JSON出力テスト",
            "content": "JSON形式で結果を確認する。",
            "supersedes": None,
            "related": None,
            "conflicts": None,
            "json": True,
        },
    )()

    result = memory.cli.handle_add(args)

    assert result == 0

    captured = capsys.readouterr()

    output = json.loads(captured.out)

    assert output["status"] == "success"
    assert output["type"] == "decision"
    assert output["title"] == "JSON出力テスト"
    assert output["path"]
    assert output["memory_id"]
    assert output["relations"] == []


def test_add_rejects_invalid_memory_type(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import MEMORY_ROOT

    args = type(
        "Args",
        (),
        {
            "type": "invalid_type",
            "title": "不正Typeテスト",
            "content": "このMemoryは作成されない。",
            "supersedes": None,
            "related": None,
            "conflicts": None,
            "json": False,
        },
    )()

    result = memory.cli.handle_add(args)

    assert result == 1

    matching = [
        path
        for path in MEMORY_ROOT.rglob("*.md")
        if path.is_file()
        and "不正Typeテスト" in path.read_text(encoding="utf-8")
    ]

    assert matching == []


def test_add_rejects_empty_title(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import MEMORY_ROOT

    args = type(
        "Args",
        (),
        {
            "type": "decision",
            "title": "   ",
            "content": "タイトルが空なので作成されない。",
            "supersedes": None,
            "related": None,
            "conflicts": None,
            "json": False,
        },
    )()

    result = memory.cli.handle_add(args)

    assert result == 1

    matching = [
        path
        for path in MEMORY_ROOT.rglob("*.md")
        if path.is_file()
        and "タイトルが空なので作成されない。" in path.read_text(
            encoding="utf-8"
        )
    ]

    assert matching == []


def test_add_rejects_empty_content(
    memory_environment,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import MEMORY_ROOT

    args = type(
        "Args",
        (),
        {
            "type": "decision",
            "title": "空Contentテスト",
            "content": "   ",
            "supersedes": None,
            "related": None,
            "conflicts": None,
            "json": False,
        },
    )()

    result = memory.cli.handle_add(args)

    assert result == 1

    matching = [
        path
        for path in MEMORY_ROOT.rglob("*.md")
        if path.is_file()
        and "空Contentテスト" in path.read_text(encoding="utf-8")
    ]

    assert matching == []


def test_ingest_prevalidation_failure_saves_nothing(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import MEMORY_ROOT

    batch_file = tmp_path / "memories.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "正常なMemory",
                    "content": "これは保存されるはずだったMemoryです。",
                },
                {
                    "type": "invalid_type",
                    "title": "不正なMemory",
                    "content": "この項目が原因で全体が拒否される。",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = [
        path
        for path in MEMORY_ROOT.rglob("*.md")
        if path.is_file()
    ]

    assert not any(
        "正常なMemory" in path.read_text(encoding="utf-8")
        for path in memories
    )

    assert not any(
        "不正なMemory" in path.read_text(encoding="utf-8")
        for path in memories
    )


def test_ingest_creates_all_valid_memories(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import MEMORY_ROOT

    batch_file = tmp_path / "memories.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "バッチMemory 1",
                    "content": "バッチで登録するMemoryその1。",
                },
                {
                    "type": "project",
                    "title": "バッチMemory 2",
                    "content": "バッチで登録するMemoryその2。",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 0

    memory_contents = [
        path.read_text(encoding="utf-8")
        for path in MEMORY_ROOT.rglob("*.md")
        if path.is_file()
    ]

    assert any("バッチMemory 1" in content for content in memory_contents)
    assert any("バッチMemory 2" in content for content in memory_contents)


def test_ingest_creates_requested_relations(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import create_memory, load_relations

    target_memory = create_memory(
        memory_type="project",
        title="既存プロジェクト",
        content="Relationの対象となる既存Memory。",
    )

    batch_file = tmp_path / "memories.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "バッチ投入された決定",
                    "content": "既存プロジェクトに関する決定事項。",
                    "related": [target_memory.stem],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 0

    relations = load_relations()

    matching = [
        relation
        for relation in relations
        if relation.get("relation") == "related"
        and relation.get("to") == target_memory.stem
    ]

    assert len(matching) == 1

    source_id = matching[0]["from"]

    assert source_id != target_memory.stem

    source_memory = next(
        path
        for path in memory.cli.MEMORY_ROOT.rglob("*.md")
        if path.stem == source_id
    )

    assert source_memory.exists()


def test_ingest_creates_supersedes_and_conflicts_relations(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import create_memory, load_relations

    superseded_memory = create_memory(
        memory_type="decision",
        title="旧方針",
        content="以前の方針。",
    )

    conflicting_memory = create_memory(
        memory_type="decision",
        title="競合する方針",
        content="別の方針。",
    )

    batch_file = tmp_path / "memories.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "新しい方針",
                    "content": "新しい決定事項。",
                    "supersedes": [superseded_memory.stem],
                    "conflicts": [conflicting_memory.stem],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 0

    relations = load_relations()

    supersedes = [
        relation
        for relation in relations
        if relation.get("relation") == "supersedes"
        and relation.get("to") == superseded_memory.stem
    ]

    conflicts = [
        relation
        for relation in relations
        if relation.get("relation") == "conflicts"
        and relation.get("to") == conflicting_memory.stem
    ]

    assert len(supersedes) == 1
    assert len(conflicts) == 1

    assert supersedes[0]["from"] == conflicts[0]["from"]


def test_ingest_reports_partial_failure_after_previous_items_are_saved(
    memory_environment,
    tmp_path,
    monkeypatch,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import create_memory

    batch_file = tmp_path / "memories.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "最初のMemory",
                    "content": "最初のMemoryは保存される。",
                },
                {
                    "type": "decision",
                    "title": "二つ目のMemory",
                    "content": "二つ目のMemoryで失敗する。",
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    original_create_memory = memory.cli.create_memory
    call_count = 0

    def failing_create_memory(*args, **kwargs):
        nonlocal call_count
        call_count += 1

        if call_count == 2:
            raise RuntimeError("simulated save failure")

        return original_create_memory(*args, **kwargs)

    monkeypatch.setattr(
        memory.cli,
        "create_memory",
        failing_create_memory,
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    titles = [
        path.read_text(encoding="utf-8").splitlines()[0]
        for path in memories
    ]

    assert any("最初のMemory" in title for title in titles)
    assert not any("二つ目のMemory" in title for title in titles)


def test_ingest_empty_batch_does_nothing(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "empty.json"

    batch_file.write_text(
        json.dumps([], ensure_ascii=False),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 0

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_missing_batch_file(
    memory_environment,
    tmp_path,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "does_not_exist.json"

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_invalid_json_file(
    memory_environment,
    tmp_path,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "invalid.json"

    batch_file.write_text(
        '{"type": "decision", "title": "壊れたJSON"',
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_non_array_json(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "object.json"

    batch_file.write_text(
        json.dumps(
            {
                "type": "decision",
                "title": "配列ではない",
                "content": "トップレベルがObject。",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_non_object_item(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "invalid_item.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "正常なMemory",
                    "content": "このMemoryは保存されてはいけない。",
                },
                "これはObjectではない",
                123,
                None,
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    # Pre-validationで失敗するため、
    # 正常な項目も含めて1件も保存されない。
    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_invalid_memory_type(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "invalid_type.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "invalid_type",
                    "title": "不正なType",
                    "content": "このMemoryは保存されてはいけない。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_normalizes_memory_type(
    memory_environment,
    tmp_path,
    monkeypatch,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "normalized_type.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "  DECISION  ",
                    "title": "Type正規化テスト",
                    "content": "大文字と前後空白を正規化して保存する。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    captured = {}

    original_create_memory = memory.cli.create_memory

    def capture_create_memory(*args, **kwargs):
        captured.update(kwargs)
        return original_create_memory(*args, **kwargs)

    monkeypatch.setattr(
        memory.cli,
        "create_memory",
        capture_create_memory,
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 0

    assert captured["memory_type"] == "decision"
    assert captured["title"] == "Type正規化テスト"
    assert captured["content"] == "大文字と前後空白を正規化して保存する。"


def test_ingest_rejects_missing_title(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "missing_title.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "content": "タイトルが存在しない。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []



def test_ingest_rejects_empty_title(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "empty_title.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "",
                    "content": "タイトルが空文字。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_whitespace_only_title(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "whitespace_title.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "   ",
                    "content": "タイトルが空白のみ。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_non_string_title(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "non_string_title.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": 12345,
                    "content": "タイトルが文字列ではない。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_missing_content(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "missing_content.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Content欠落テスト",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_empty_content(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "empty_content.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Content空文字テスト",
                    "content": "",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_whitespace_only_content(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "whitespace_content.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Content空白テスト",
                    "content": "   ",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []



def test_ingest_rejects_non_string_content(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "non_string_content.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Content型テスト",
                    "content": 12345,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_non_array_related(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "invalid_related.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Related型テスト",
                    "content": "relatedが配列ではない。",
                    "related": "not-an-array",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_non_array_supersedes(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "invalid_supersedes.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Supersedes型テスト",
                    "content": "supersedesが配列ではない。",
                    "supersedes": "not-an-array",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_non_array_conflicts(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "invalid_conflicts.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Conflicts型テスト",
                    "content": "conflictsが配列ではない。",
                    "conflicts": "not-an-array",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_empty_related_memory_id(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "empty_related_id.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Related ID空文字テスト",
                    "content": "relatedに空文字IDを指定する。",
                    "related": [""],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_non_string_related_memory_id(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "non_string_related_id.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Related ID型テスト",
                    "content": "relatedに数値IDを指定する。",
                    "related": [12345],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_missing_related_memory_id(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "missing_related_id.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Related存在確認テスト",
                    "content": "存在しないMemory IDをrelatedに指定する。",
                    "related": ["20260815_000000_000000_missing_Memory"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_missing_supersedes_memory_id(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "missing_supersedes_id.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Supersedes存在確認テスト",
                    "content": "存在しないMemory IDをsupersedesに指定する。",
                    "supersedes": ["20260815_000000_000000_missing_Memory"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_rejects_missing_conflicts_memory_id(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "missing_conflicts_id.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Conflicts存在確認テスト",
                    "content": "存在しないMemory IDをconflictsに指定する。",
                    "conflicts": ["20260815_000000_000000_missing_Memory"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_accepts_existing_related_memory(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import create_memory, load_relations

    target_memory = create_memory(
        memory_type="project",
        title="既存Related対象",
        content="既存のMemory。",
    )

    batch_file = tmp_path / "existing_related.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Related正常系テスト",
                    "content": "既存Memoryをrelatedとして指定する。",
                    "related": [target_memory.stem],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 0

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert len(memories) == 2

    relations = load_relations()

    source_memory = next(
        memory
        for memory in memories
        if memory.stem != target_memory.stem
    )

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
        and relation.get("to") == target_memory.stem
    ]

    assert len(matching) == 1


def test_ingest_accepts_existing_supersedes_memory(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import create_memory, load_relations

    target_memory = create_memory(
        memory_type="decision",
        title="旧方針",
        content="以前の方針。",
    )

    batch_file = tmp_path / "existing_supersedes.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "新方針",
                    "content": "既存Memoryをsupersedesとして指定する。",
                    "supersedes": [target_memory.stem],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 0

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert len(memories) == 2

    relations = load_relations()

    source_memory = next(
        memory
        for memory in memories
        if memory.stem != target_memory.stem
    )

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "supersedes"
        and relation.get("to") == target_memory.stem
    ]

    assert len(matching) == 1


def test_ingest_accepts_existing_conflicts_memory(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import create_memory, load_relations

    target_memory = create_memory(
        memory_type="decision",
        title="対立する旧方針",
        content="別の方針。",
    )

    batch_file = tmp_path / "existing_conflicts.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "新方針",
                    "content": "既存Memoryをconflictsとして指定する。",
                    "conflicts": [target_memory.stem],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 0

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert len(memories) == 2

    relations = load_relations()

    source_memory = next(
        memory
        for memory in memories
        if memory.stem != target_memory.stem
    )

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "conflicts"
        and relation.get("to") == target_memory.stem
    ]

    assert len(matching) == 1


def test_ingest_rejects_relation_to_memory_created_in_same_batch(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "same_batch_relation.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "project",
                    "title": "先に作るMemory",
                    "content": "同一バッチ内の対象Memory。",
                },
                {
                    "type": "decision",
                    "title": "後から作るMemory",
                    "content": "同一バッチ内のMemoryをrelatedに指定する。",
                    "related": ["SAME_BATCH_TARGET"],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 1

    memories = list(memory.cli.MEMORY_ROOT.rglob("*.md"))

    assert memories == []


def test_ingest_accepts_archived_memory_as_relation_target(
    memory_environment,
    tmp_path,
):
    import importlib
    import json
    import shutil

    import memory.cli
    import memory.long_term

    importlib.reload(memory.long_term)
    importlib.reload(memory.cli)

    from memory.long_term import create_memory, load_relations

    target_memory = create_memory(
        memory_type="decision",
        title="過去の方針",
        content="Archiveへ移動済みのMemory。",
    )

    archive_path = memory.long_term.ARCHIVE_ROOT / target_memory.name
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    shutil.move(
        str(target_memory),
        str(archive_path),
    )

    batch_file = tmp_path / "archived_relation_target.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Archive対象Relationテスト",
                    "content": "Archive済みMemoryをrelatedとして指定する。",
                    "related": [target_memory.stem],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 0

    active_memories = [
        path
        for path in memory.cli.MEMORY_ROOT.rglob("*.md")
        if memory.long_term.ARCHIVE_ROOT not in path.parents
    ]

    assert len(active_memories) == 1

    assert archive_path.exists()

    relations = load_relations()

    source_memory = active_memories[0]

    matching = [
        relation
        for relation in relations
        if relation.get("from") == source_memory.stem
        and relation.get("relation") == "related"
        and relation.get("to") == target_memory.stem
    ]

    assert len(matching) == 1


def test_ingest_creates_all_relation_types_for_one_memory(
    memory_environment,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    from memory.long_term import create_memory, load_relations

    related_memory = create_memory(
        memory_type="project",
        title="関連Memory",
        content="Related対象。",
    )

    superseded_memory = create_memory(
        memory_type="decision",
        title="旧方針",
        content="Supersedes対象。",
    )

    conflicting_memory = create_memory(
        memory_type="decision",
        title="対立方針",
        content="Conflicts対象。",
    )

    batch_file = tmp_path / "all_relation_types.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "Relation一括テスト",
                    "content": "3種類のRelationを同時に指定する。",
                    "related": [related_memory.stem],
                    "supersedes": [superseded_memory.stem],
                    "conflicts": [conflicting_memory.stem],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    result = memory.cli.handle_ingest(args)

    assert result == 0

    memories = [
        path
        for path in memory.cli.MEMORY_ROOT.rglob("*.md")
        if memory.cli.ARCHIVE_ROOT not in path.parents
    ]

    assert len(memories) == 4

    source_memory = next(
        memory
        for memory in memories
        if memory.stem
        not in {
            related_memory.stem,
            superseded_memory.stem,
            conflicting_memory.stem,
        }
    )

    relations = load_relations()

    expected_relations = {
        ("related", related_memory.stem),
        ("supersedes", superseded_memory.stem),
        ("conflicts", conflicting_memory.stem),
    }

    actual_relations = {
        (relation.get("relation"), relation.get("to"))
        for relation in relations
        if relation.get("from") == source_memory.stem
    }

    assert actual_relations == expected_relations


def test_main_ingest_dispatches_to_handle_ingest(
    monkeypatch,
    tmp_path,
):
    import importlib
    import json

    import memory.cli

    importlib.reload(memory.cli)

    batch_file = tmp_path / "dispatch.json"

    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "CLI Dispatch Test",
                    "content": "mainからingestへ正しく到達することを確認する。",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    called = {}

    def fake_handle_ingest(args):
        called["file"] = args.file
        return 37

    monkeypatch.setattr(
        memory.cli,
        "handle_ingest",
        fake_handle_ingest,
    )

    monkeypatch.setattr(
        memory.cli.sys,
        "argv",
        [
            "memory.cli",
            "ingest",
            "--file",
            str(batch_file),
        ],
    )

    result = memory.cli.main()

    assert result == 37
    assert called["file"] == str(batch_file)


def test_main_ingest_requires_file_argument(
    monkeypatch,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    monkeypatch.setattr(
        memory.cli.sys,
        "argv",
        [
            "memory.cli",
            "ingest",
        ],
    )

    import pytest

    with pytest.raises(SystemExit) as exc_info:
        memory.cli.main()

    assert exc_info.value.code == 2


def test_main_ingest_returns_error_for_missing_batch_file(
    monkeypatch,
    tmp_path,
):
    import importlib

    import memory.cli

    importlib.reload(memory.cli)

    missing_file = tmp_path / "does_not_exist.json"

    monkeypatch.setattr(
        memory.cli.sys,
        "argv",
        [
            "memory.cli",
            "ingest",
            "--file",
            str(missing_file),
        ],
    )

    result = memory.cli.main()

    assert result == 1


def test_add_executes_relation_reevaluation(
    memory_environment,
    monkeypatch,
):
    """
    handle_add must run auto relation re-evaluation after saving the memory.
    """
    import importlib
    import memory.cli
    from memory.long_term import create_memory, load_relations

    importlib.reload(memory.cli)

    existing_mem = create_memory(
        memory_type="decision",
        title="旧方針",
        content="旧方針を採用する。",
    )
    existing_id = existing_mem.stem

    monkeypatch.setattr(
        "memory.memory_relation.find_memory_candidates",
        lambda title, content: [
            {"id": existing_id, "path": str(existing_mem), "content": "旧方針を採用する。", "score": 10}
        ],
    )

    monkeypatch.setattr(
        "memory.memory_relation.analyze_memory_relations",
        lambda title, content, candidates: [
            {"id": existing_id, "relation": "supersedes"}
        ],
    )

    args = type(
        "Args",
        (),
        {
            "type": "decision",
            "title": "新方針",
            "content": "旧方針を廃止し新方針へ変更する。",
            "supersedes": None,
            "related": None,
            "conflicts": None,
            "json": True,
        },
    )()

    exit_code = memory.cli.handle_add(args)
    assert exit_code == 0

    relations = load_relations()
    assert any(
        r.get("relation") == "supersedes" and r.get("to") == existing_id
        for r in relations
    )


def test_ingest_executes_relation_reevaluation_against_existing_memories(
    memory_environment,
    monkeypatch,
    tmp_path,
):
    """
    handle_ingest must run auto relation re-evaluation for ingested items against existing store memories.
    """
    import importlib
    import json
    import memory.cli
    from memory.long_term import create_memory, load_relations

    importlib.reload(memory.cli)

    existing_mem = create_memory(
        memory_type="decision",
        title="既存仕様",
        content="既存の仕様",
    )
    existing_id = existing_mem.stem

    batch_file = tmp_path / "ingest_auto_rel.json"
    batch_file.write_text(
        json.dumps(
            [
                {
                    "type": "decision",
                    "title": "新規仕様",
                    "content": "既存仕様を更新する新規仕様",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "memory.memory_relation.find_memory_candidates",
        lambda title, content: [
            {"id": existing_id, "path": str(existing_mem), "content": "既存の仕様", "score": 10}
        ],
    )

    monkeypatch.setattr(
        "memory.memory_relation.analyze_memory_relations",
        lambda title, content, candidates: [
            {"id": existing_id, "relation": "supersedes"}
        ],
    )

    args = type(
        "Args",
        (),
        {
            "file": str(batch_file),
        },
    )()

    exit_code = memory.cli.handle_ingest(args)
    assert exit_code == 0

    relations = load_relations()
    assert any(
        r.get("relation") == "supersedes" and r.get("to") == existing_id
        for r in relations
    )

