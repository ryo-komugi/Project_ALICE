import pytest

from memory.memory_router import should_use_memory


@pytest.mark.integration
def test_should_use_memory_returns_true_for_past_project_decision():
    """
    Verify that a question referring to a past Project_ALICE
    decision is routed to long-term Memory.
    """

    question = (
        "Project_ALICEで以前決めた外部インターフェースについて教えて"
    )

    result = should_use_memory(question)

    assert result is True


@pytest.mark.integration
def test_should_use_memory_returns_false_for_general_programming_question():
    """
    Verify that a general programming question does not require
    long-term Memory.
    """

    question = (
        "Pythonで辞書をJSONに変換する方法を教えて"
    )

    result = should_use_memory(question)

    assert result is False