from memory.long_term import create_memory


def test_memory_environment_is_isolated(memory_environment):
    path = create_memory(
        memory_type="decision",
        title="テストMemory",
        content="これはテスト用Memoryです。",
    )

    assert path.exists()
    assert str(path).startswith(str(memory_environment))