import importlib

import pytest


@pytest.fixture
def memory_environment(tmp_path, monkeypatch):
    """
    Create an isolated Memory environment for one test.

    The production Memory root is never modified.
    """

    root = tmp_path / "memory"
    obsidian_root = tmp_path / "obsidian"

    monkeypatch.setenv(
        "ALICE_COPILOT_MEMORY_ROOT",
        str(root),
    )

    # Reload configuration after changing the environment.
    import config

    importlib.reload(config)

    # Override the Obsidian root for the isolated test environment.
    monkeypatch.setattr(
        config,
        "OBSIDIAN_ROOT",
        obsidian_root,
    )

    # Reload modules which cache configuration values at import time.
    import memory.long_term
    import memory.memory_search
    import memory.memory_relation
    import memory.obsidian_export

    importlib.reload(memory.long_term)
    importlib.reload(memory.memory_search)
    importlib.reload(memory.memory_relation)
    importlib.reload(memory.obsidian_export)

    return root