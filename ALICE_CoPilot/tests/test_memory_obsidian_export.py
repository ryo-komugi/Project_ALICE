from pathlib import Path

import config
from memory.long_term import create_memory, create_relation
from memory.obsidian_export import (
    export_memory,
    export_all_memories,
)


def test_export_memory_creates_obsidian_file(memory_environment):
    memory = create_memory(
        memory_type="decision",
        title="テスト決定",
        content="これはテスト用のMemoryです。",
    )

    exported = export_memory(memory)

    assert exported.exists()
    assert exported.parent == config.OBSIDIAN_ROOT / "Decisions"

    content = exported.read_text(encoding="utf-8")

    assert "# テスト決定" in content
    assert "これはテスト用のMemoryです。" in content


def test_export_memory_exports_related_relation(memory_environment):
    source = create_memory(
        memory_type="decision",
        title="A",
        content="Aの内容",
    )

    target = create_memory(
        memory_type="knowledge",
        title="B",
        content="Bの内容",
    )

    create_relation(
        from_memory_id=source.stem,
        relation="related",
        to_memory_id=target.stem,
    )

    exported = export_memory(source)

    content = exported.read_text(encoding="utf-8")

    assert "## Relations" in content
    assert "### Related" in content
    assert f"[[{target.stem}]]" in content


def test_export_memory_preserves_supersedes_direction(memory_environment):
    old_memory = create_memory(
        memory_type="decision",
        title="旧方式",
        content="旧方式の内容",
    )

    new_memory = create_memory(
        memory_type="decision",
        title="新方式",
        content="新方式の内容",
    )

    create_relation(
        from_memory_id=new_memory.stem,
        relation="supersedes",
        to_memory_id=old_memory.stem,
    )

    exported = export_memory(new_memory)

    content = exported.read_text(encoding="utf-8")

    assert "### Supersedes" in content
    assert f"[[{old_memory.stem}]]" in content


def test_export_memory_shows_superseded_by(memory_environment):
    old_memory = create_memory(
        memory_type="decision",
        title="旧方式",
        content="旧方式の内容",
    )

    new_memory = create_memory(
        memory_type="decision",
        title="新方式",
        content="新方式の内容",
    )

    create_relation(
        from_memory_id=new_memory.stem,
        relation="supersedes",
        to_memory_id=old_memory.stem,
    )

    exported = export_memory(old_memory)

    content = exported.read_text(encoding="utf-8")

    assert "### Superseded By" in content
    assert f"[[{new_memory.stem}]]" in content


def test_export_memory_shows_conflicts(memory_environment):
    memory_a = create_memory(
        memory_type="decision",
        title="方式A",
        content="A",
    )

    memory_b = create_memory(
        memory_type="decision",
        title="方式B",
        content="B",
    )

    create_relation(
        from_memory_id=memory_a.stem,
        relation="conflicts",
        to_memory_id=memory_b.stem,
    )

    exported = export_memory(memory_a)

    content = exported.read_text(encoding="utf-8")

    assert "### Conflicts" in content
    assert f"[[{memory_b.stem}]]" in content


def test_export_does_not_modify_source_memory(memory_environment):
    memory = create_memory(
        memory_type="decision",
        title="不変Memory",
        content="元の内容",
    )

    original = memory.read_text(encoding="utf-8")

    export_memory(memory)

    assert memory.read_text(encoding="utf-8") == original


def test_export_all_memories(memory_environment):
    memory_a = create_memory(
        memory_type="decision",
        title="A",
        content="A",
    )

    memory_b = create_memory(
        memory_type="knowledge",
        title="B",
        content="B",
    )

    exported = export_all_memories()

    assert len(exported) == 2

    exported_names = {
        path.name
        for path in exported
    }

    assert memory_a.name in exported_names
    assert memory_b.name in exported_names


def test_sync_obsidian_dry_run_detects_obsolete_file(memory_environment):
    from memory.long_term import create_memory
    from memory.obsidian_export import export_memory, sync_obsidian

    memory = create_memory(
        memory_type="decision",
        title="Current",
        content="Current memory",
    )

    exported = export_memory(memory)

    obsolete = exported.parent / "obsolete_memory.md"
    obsolete.write_text(
        "# Obsolete\n\nThis should be detected.\n",
        encoding="utf-8",
    )

    result = sync_obsidian(dry_run=True)

    assert obsolete in result["obsolete"]
    assert obsolete.exists()


def test_sync_obsidian_dry_run_does_not_modify_files(memory_environment):
    from memory.long_term import create_memory
    from memory.obsidian_export import export_memory, sync_obsidian

    memory = create_memory(
        memory_type="decision",
        title="Current",
        content="Current memory",
    )

    exported = export_memory(memory)

    original_content = exported.read_text(encoding="utf-8")

    obsolete = exported.parent / "obsolete_memory.md"
    obsolete.write_text(
        "# Obsolete\n",
        encoding="utf-8",
    )

    result = sync_obsidian(dry_run=True)

    assert result["errors"] == []
    assert exported.read_text(encoding="utf-8") == original_content
    assert obsolete.exists()


def test_sync_obsidian_clean_removes_obsolete_file(memory_environment):
    from memory.long_term import create_memory
    from memory.obsidian_export import export_memory, sync_obsidian

    memory = create_memory(
        memory_type="decision",
        title="Current",
        content="Current memory",
    )

    export_memory(memory)

    obsolete = memory.parent.parent / "obsidian" / "Decisions" / "obsolete_memory.md"

    # Use the configured Obsidian root instead of assuming a fixed path.
    import config

    obsolete = config.OBSIDIAN_ROOT / "Decisions" / "obsolete_memory.md"
    obsolete.parent.mkdir(parents=True, exist_ok=True)
    obsolete.write_text(
        "# Obsolete\n",
        encoding="utf-8",
    )

    result = sync_obsidian(clean=True)

    assert result["errors"] == []
    assert obsolete in result["deleted"]
    assert not obsolete.exists()


def test_sync_obsidian_does_not_manage_unknown_directories(memory_environment):
    from memory.long_term import create_memory
    from memory.obsidian_export import export_memory, sync_obsidian

    memory = create_memory(
        memory_type="decision",
        title="Current",
        content="Current memory",
    )

    export_memory(memory)

    import config

    custom_note = config.OBSIDIAN_ROOT / "Notes" / "my_note.md"
    custom_note.parent.mkdir(parents=True, exist_ok=True)
    custom_note.write_text(
        "# My Note\n",
        encoding="utf-8",
    )

    result = sync_obsidian(
        dry_run=True,
    )

    assert custom_note not in result["obsolete"]
    assert custom_note.exists()