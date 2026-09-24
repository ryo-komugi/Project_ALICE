import json
import pytest
from memory.memory_relation import analyze_memory_relations


def test_historical_memory_cannot_be_superseded(
    monkeypatch,
):
    """
    Historical Memory must never become a direct
    supersedes target, even when the LLM returns
    supersedes for that candidate.
    """

    historical_memory_id = (
        "20260813_230700_806316_f31e_"
        "supersedesテストにおける方式変更の決定"
    )

    candidates = [
        {
            "id": historical_memory_id,
            "path": "",
            "content": (
                "supersedesテストにおいて、"
                "旧方式の方式Aを廃止し、"
                "方式Bへと変更することが決定した。"
            ),
            "score": 10,
        }
    ]

    # ---------------------------------------------------------
    # Mock Ollama response.
    #
    # Intentionally return an invalid supersedes decision:
    # the candidate is Historical Memory.
    # ---------------------------------------------------------

    class FakeResponse:
        status_code = 200
        text = (
            '{"message":{"content":'
            '"{\\"relations\\":[{'
            '\\"candidate\\":1,'
            '\\"relation\\":\\"supersedes\\"'
            '}]}"}}'
        )

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self.text)

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    # ---------------------------------------------------------
    # Tell the test that this candidate is Historical.
    # ---------------------------------------------------------

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: {historical_memory_id},
    )

    # ---------------------------------------------------------
    # Execute relation analysis.
    # ---------------------------------------------------------

    relations = analyze_memory_relations(
        title="supersedesテストの追加変更",
        content=(
            "supersedesテストでは、"
            "方式Bを廃止して方式Cへ変更する。"
        ),
        candidates=candidates,
    )

    # ---------------------------------------------------------
    # The LLM said "supersedes", but the candidate is
    # Historical Memory.
    #
    # Therefore the code-side validation must reject it.
    # ---------------------------------------------------------

    assert relations == []

def test_current_memory_can_be_superseded(
    monkeypatch,
):
    """
    Current Memory may become a direct supersedes target
    when the LLM determines that the new Memory supersedes it.
    """

    current_memory_id = (
        "20260813_230926_749497_9af9_"
        "supersedesテストの実施方法"
    )

    candidates = [
        {
            "id": current_memory_id,
            "path": "",
            "content": (
                "supersedesテストでは、"
                "方式Aを使用しないこと。"
            ),
            "score": 10,
        }
    ]

    # ---------------------------------------------------------
    # Mock Ollama response.
    #
    # The LLM determines that the Current Memory
    # is superseded by the new Memory.
    # ---------------------------------------------------------

    class FakeResponse:
        status_code = 200
        text = (
            '{"message":{"content":'
            '"{\\"relations\\":[{'
            '\\"candidate\\":1,'
            '\\"relation\\":\\"supersedes\\"'
            '}]}"}}'
        )

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self.text)

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    # ---------------------------------------------------------
    # This Memory is NOT included in the superseded set.
    # Therefore it is a Current Memory.
    # ---------------------------------------------------------

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    # ---------------------------------------------------------
    # Execute relation analysis.
    # ---------------------------------------------------------

    relations = analyze_memory_relations(
        title="supersedesテストの方式変更",
        content=(
            "supersedesテストでは、"
            "方式Aを廃止して方式Bへ変更する。"
        ),
        candidates=candidates,
    )

    # ---------------------------------------------------------
    # Current Memory is a valid supersedes target.
    # ---------------------------------------------------------

    assert relations == [
        {
            "id": current_memory_id,
            "relation": "supersedes",
        }
    ]


def test_supersedes_allows_only_one_current_target(
    monkeypatch,
):
    """
    Even when the LLM returns multiple supersedes relations,
    only one Current Memory may become a direct supersedes target.
    """

    current_memory_id_1 = (
        "20260813_230926_749497_9af9_"
        "supersedesテストの実施方法"
    )

    current_memory_id_2 = (
        "20260813_230700_806316_f31e_"
        "supersedesテストにおける方式変更の決定"
    )

    candidates = [
        {
            "id": current_memory_id_1,
            "path": "",
            "content": (
                "supersedesテストでは、"
                "方式Aを使用しないこと。"
            ),
            "score": 10,
        },
        {
            "id": current_memory_id_2,
            "path": "",
            "content": (
                "supersedesテストにおいて、"
                "旧方式の方式Aを廃止し、"
                "方式Bへと変更することが決定した。"
            ),
            "score": 9,
        },
    ]

    # ---------------------------------------------------------
    # Mock Ollama response.
    #
    # Intentionally return TWO supersedes relations.
    # ---------------------------------------------------------

    class FakeResponse:
        status_code = 200
        text = (
            '{"message":{"content":'
            '"{\\"relations\\":['
            '{\\"candidate\\":1,\\"relation\\":\\"supersedes\\"},'
            '{\\"candidate\\":2,\\"relation\\":\\"supersedes\\"}'
            ']}"}}'
        )

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self.text)

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    # ---------------------------------------------------------
    # Neither candidate is Historical.
    # Both are Current Memories.
    # ---------------------------------------------------------

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    # ---------------------------------------------------------
    # Execute relation analysis.
    # ---------------------------------------------------------

    relations = analyze_memory_relations(
        title="supersedesテストの追加変更",
        content=(
            "supersedesテストでは、"
            "方式Bを廃止して方式Cへ変更する。"
        ),
        candidates=candidates,
    )

    # ---------------------------------------------------------
    # Only one supersedes relation may be returned.
    # ---------------------------------------------------------

    assert len(relations) == 1
    assert relations[0]["relation"] == "supersedes"


def test_related_relation_is_accepted(
    monkeypatch,
):
    """
    A valid related relation returned by the LLM
    is accepted as-is.
    """

    related_memory_id = (
        "20260813_224657_461548_5f0a_"
        "MemoryManager実接続テスト完了"
    )

    candidates = [
        {
            "id": related_memory_id,
            "path": "",
            "content": (
                "MemoryManagerの実接続テストが完了した。"
            ),
            "score": 10,
        }
    ]

    class FakeResponse:
        status_code = 200
        text = (
            '{"message":{"content":'
            '"{\\"relations\\":[{'
            '\\"candidate\\":1,'
            '\\"relation\\":\\"related\\"'
            '}]}"}}'
        )

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self.text)

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    relations = analyze_memory_relations(
        title="MemoryManagerテストに関する追加情報",
        content=(
            "MemoryManagerの実接続テストに関連する"
            "追加情報を記録する。"
        ),
        candidates=candidates,
    )

    assert relations == [
        {
            "id": related_memory_id,
            "relation": "related",
        }
    ]


def test_conflicts_relation_is_accepted(
    monkeypatch,
):
    """
    A valid conflicts relation returned by the LLM
    is accepted as-is.
    """

    conflicting_memory_id = (
        "20260813_230700_806316_f31e_"
        "supersedesテストにおける方式変更の決定"
    )

    candidates = [
        {
            "id": conflicting_memory_id,
            "path": "",
            "content": (
                "supersedesテストでは、"
                "方式Aから方式Bへ変更することが決定した。"
            ),
            "score": 10,
        }
    ]

    class FakeResponse:
        status_code = 200
        text = (
            '{"message":{"content":'
            '"{\\"relations\\":[{'
            '\\"candidate\\":1,'
            '\\"relation\\":\\"conflicts\\"'
            '}]}"}}'
        )

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self.text)

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    relations = analyze_memory_relations(
        title="supersedesテストの別方式",
        content=(
            "supersedesテストでは、"
            "方式Cを使用する。"
        ),
        candidates=candidates,
    )

    assert relations == [
        {
            "id": conflicting_memory_id,
            "relation": "conflicts",
        }
    ]


def test_invalid_candidate_number_is_ignored(
    monkeypatch,
):
    """
    LLM returns a candidate number that does not exist
    in the candidate list.

    The invalid relation must be ignored.
    """

    current_memory_id = (
        "20260813_230926_749497_9af9_"
        "supersedesテストの実施方法"
    )

    candidates = [
        {
            "id": current_memory_id,
            "path": "",
            "content": (
                "supersedesテストでは、"
                "方式Aを使用しないこと。"
            ),
            "score": 10,
        }
    ]

    class FakeResponse:
        status_code = 200
        text = (
            '{"message":{"content":'
            '"{\\"relations\\":[{'
            '\\"candidate\\":99,'
            '\\"relation\\":\\"related\\"'
            '}]}"}}'
        )

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self.text)

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    relations = analyze_memory_relations(
        title="supersedesテストの追加情報",
        content="追加のテスト情報です。",
        candidates=candidates,
    )

    assert relations == []


def test_invalid_relation_type_is_ignored(
    monkeypatch,
):
    """
    LLM returns an unsupported relation type.

    The invalid relation must be ignored.
    """

    current_memory_id = (
        "20260813_230926_749497_9af9_"
        "supersedesテストの実施方法"
    )

    candidates = [
        {
            "id": current_memory_id,
            "path": "",
            "content": (
                "supersedesテストでは、"
                "方式Aを使用しないこと。"
            ),
            "score": 10,
        }
    ]

    class FakeResponse:
        status_code = 200
        text = (
            '{"message":{"content":'
            '"{\\"relations\\":[{'
            '\\"candidate\\":1,'
            '\\"relation\\":\\"unknown_relation\\"'
            '}]}"}}'
        )

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self.text)

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    relations = analyze_memory_relations(
        title="supersedesテストの追加情報",
        content="追加のテスト情報です。",
        candidates=candidates,
    )

    assert relations == []


def test_invalid_llm_json_returns_empty_relations(
    monkeypatch,
):
    """
    When the LLM returns invalid JSON,
    relation analysis must fail safely and return no relations.
    """

    current_memory_id = (
        "20260813_230926_749497_9af9_"
        "supersedesテストの実施方法"
    )

    candidates = [
        {
            "id": current_memory_id,
            "path": "",
            "content": (
                "supersedesテストでは、"
                "方式Aを使用しないこと。"
            ),
            "score": 10,
        }
    ]

    class FakeResponse:
        status_code = 200

        # message.content itself is NOT valid JSON.
        text = (
            '{"message":{"content":'
            '"this is not valid json"'
            '}}'
        )

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self.text)

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    relations = analyze_memory_relations(
        title="supersedesテストの追加変更",
        content=(
            "supersedesテストでは、"
            "方式Bを廃止して方式Cへ変更する。"
        ),
        candidates=candidates,
    )

    assert relations == []


def test_non_list_relations_returns_empty_relations(
    monkeypatch,
):
    """
    When the LLM returns a non-list value for "relations",
    relation analysis must fail safely and return no relations.
    """

    current_memory_id = (
        "20260813_230926_749497_9af9_"
        "supersedesテストの実施方法"
    )

    candidates = [
        {
            "id": current_memory_id,
            "path": "",
            "content": (
                "supersedesテストでは、"
                "方式Aを使用しないこと。"
            ),
            "score": 10,
        }
    ]

    class FakeResponse:
        status_code = 200
        text = (
            '{"message":{"content":'
            '"{\\"relations\\":\\"invalid\\"}"'
            '}}'
        )

        def raise_for_status(self):
            pass

        def json(self):
            return json.loads(self.text)

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    relations = analyze_memory_relations(
        title="supersedesテストの追加変更",
        content=(
            "supersedesテストでは、"
            "方式Bを廃止して方式Cへ変更する。"
        ),
        candidates=candidates,
    )

    assert relations == []


def test_invalid_relation_items_are_ignored(
    monkeypatch,
):
    """
    When the LLM returns non-dict items inside the relations list,
    those items must be ignored without affecting valid relations.
    """

    current_memory_id = (
        "20260813_230926_749497_9af9_"
        "supersedesテストの実施方法"
    )

    candidates = [
        {
            "id": current_memory_id,
            "path": "",
            "content": (
                "supersedesテストでは、"
                "方式Aを使用しないこと。"
            ),
            "score": 10,
        }
    ]

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "message": {
                    "content": json.dumps(
                        {
                            "relations": [
                                None,
                                "invalid",
                                123,
                                {
                                    "candidate": 1,
                                    "relation": "related",
                                },
                            ]
                        }
                    )
                }
            }

        @property
        def text(self):
            return json.dumps(self.json())

    def fake_post(*args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    relations = analyze_memory_relations(
        title="supersedesテストの追加情報",
        content="supersedesテストに関する追加情報です。",
        candidates=candidates,
    )

    assert relations == [
        {
            "id": current_memory_id,
            "relation": "related",
        }
    ]


def test_analyze_memory_relations_filters_candidates_by_subject(
    monkeypatch,
):
    """
    Relation analysis must apply Subject filtering before
    sending candidates to the LLM.
    """

    candidates = [
        {
            "id": "matching-memory",
            "path": "",
            "content": (
                "# M3-4-4 のMemory\n\n"
                "M3-4-4 に関する決定事項です。\n"
            ),
            "score": 10,
        },
        {
            "id": "different-memory",
            "path": "",
            "content": (
                "# M3-4-5 のMemory\n\n"
                "M3-4-5 に関する決定事項です。\n"
            ),
            "score": 9,
        },
    ]

    captured = {}

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    def fake_post(*args, **kwargs):
        captured["payload"] = kwargs["json"]

        class FakeResponse:
            status_code = 200
            text = (
                '{"message":{"content":'
                '"{\\"relations\\":[]}"'
                '}}'
            )

            def raise_for_status(self):
                pass

            def json(self):
                return json.loads(self.text)

        return FakeResponse()

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fake_post,
    )

    relations = analyze_memory_relations(
        title="M3-4-4 の新しい決定",
        content="M3-4-4 に関する追加の決定事項です。",
        candidates=candidates,
    )

    assert relations == []

    prompt = captured["payload"]["messages"][1]["content"]

    assert "matching-memory" in prompt
    assert "different-memory" not in prompt


def test_analyze_memory_relations_skips_llm_when_subject_filter_removes_all_candidates(
    monkeypatch,
):
    """
    When Subject filtering removes every candidate,
    relation analysis must return immediately without calling the LLM.
    """

    candidates = [
        {
            "id": "different-memory",
            "path": "",
            "content": (
                "# M3-4-5 のMemory\n\n"
                "M3-4-5 に関する決定事項です。\n"
            ),
            "score": 10,
        },
    ]

    def fail_post(*args, **kwargs):
        raise AssertionError(
            "LLM must not be called when no candidates remain "
            "after Subject filtering."
        )

    monkeypatch.setattr(
        "memory.memory_relation.requests.post",
        fail_post,
    )

    monkeypatch.setattr(
        "memory.memory_relation.find_superseded_memory_ids",
        lambda: set(),
    )

    relations = analyze_memory_relations(
        title="M3-4-4 の新しい決定",
        content="M3-4-4 に関する追加の決定事項です。",
        candidates=candidates,
    )

    assert relations == []


def test_supersedes_chain_keeps_only_latest_memory_current(
    memory_environment,
):
    """
    A supersedes chain must leave only the latest Memory current.

    A <- B <- C
    where:
        B supersedes A
        C supersedes B

    A and B must be Historical.
    C must remain Current.
    """

    from memory.long_term import (
        create_memory,
        create_relation,
    )
    from memory.memory_relation import (
        find_superseded_memory_ids,
    )

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

    superseded_ids = find_superseded_memory_ids()

    assert memory_a.stem in superseded_ids
    assert memory_b.stem in superseded_ids
    assert memory_c.stem not in superseded_ids


def test_supersedes_cycle_is_rejected(
    memory_environment,
):
    """
    supersedes relations must not form a cycle.

    A <- B <- C
    must reject:
        C -> supersedes -> A
    """

    from memory.long_term import (
        create_memory,
        create_relation,
    )

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

    with pytest.raises(ValueError):
        create_relation(
            from_memory_id=memory_a.stem,
            relation="supersedes",
            to_memory_id=memory_c.stem,
        )


def test_supersedes_cycle_rejection_does_not_create_relation(
    memory_environment,
):
    """
    Rejecting a supersedes cycle must not create a Relation file.
    """

    from memory.long_term import (
        create_memory,
        create_relation,
        load_relations,
    )

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

    create_relation(
        from_memory_id=memory_b.stem,
        relation="supersedes",
        to_memory_id=memory_a.stem,
    )

    before = load_relations()

    with pytest.raises(ValueError):
        create_relation(
            from_memory_id=memory_a.stem,
            relation="supersedes",
            to_memory_id=memory_b.stem,
        )

    after = load_relations()

    assert after == before


def test_reevaluate_relations_creates_and_persists_relation(
    memory_environment,
    monkeypatch,
):
    """
    reevaluate_relations_for_memory must perform relation analysis and persist created relation JSON files.
    """
    from memory.long_term import create_memory, load_relations
    from memory.memory_relation import reevaluate_relations_for_memory

    existing_mem = create_memory(
        memory_type="decision",
        title="旧方式",
        content="方式Aを使用する。",
    )
    existing_id = existing_mem.stem

    new_mem = create_memory(
        memory_type="decision",
        title="新方式",
        content="方式Aを廃止し方式Bを採用する。",
    )
    new_id = new_mem.stem

    monkeypatch.setattr(
        "memory.memory_relation.find_memory_candidates",
        lambda title, content: [
            {"id": existing_id, "path": str(existing_mem), "content": "方式Aを使用する。", "score": 10}
        ],
    )

    monkeypatch.setattr(
        "memory.memory_relation.analyze_memory_relations",
        lambda title, content, candidates: [
            {"id": existing_id, "relation": "supersedes"}
        ],
    )

    created = reevaluate_relations_for_memory(
        memory_id=new_id,
        title="新方式",
        content="方式Aを廃止し方式Bを採用する。",
    )

    assert len(created) == 1
    assert created[0]["relation"] == "supersedes"
    assert created[0]["memory_id"] == existing_id

    relations = load_relations()
    assert any(
        r.get("from") == new_id
        and r.get("relation") == "supersedes"
        and r.get("to") == existing_id
        for r in relations
    )


def test_reevaluate_relations_excludes_target_and_exclude_ids(
    memory_environment,
    monkeypatch,
):
    """
    reevaluate_relations_for_memory must exclude the target memory_id and any exclude_ids from candidates.
    """
    from memory.memory_relation import reevaluate_relations_for_memory

    analyzed_candidates = []

    def fake_analyze(title, content, candidates):
        nonlocal analyzed_candidates
        analyzed_candidates = candidates
        return []

    monkeypatch.setattr(
        "memory.memory_relation.analyze_memory_relations",
        fake_analyze,
    )

    candidates = [
        {"id": "target_id", "content": "Target", "score": 10},
        {"id": "batch_item_1", "content": "Same batch item", "score": 9},
        {"id": "pre_existing_id", "content": "Pre-existing item", "score": 8},
    ]

    reevaluate_relations_for_memory(
        memory_id="target_id",
        title="Test Title",
        content="Test Content",
        candidates=candidates,
        exclude_ids={"batch_item_1"},
    )

    candidate_ids = [c["id"] for c in analyzed_candidates]
    assert "target_id" not in candidate_ids
    assert "batch_item_1" not in candidate_ids
    assert "pre_existing_id" in candidate_ids


def test_reevaluate_relations_prevents_duplicate_relations(
    memory_environment,
    monkeypatch,
):
    """
    reevaluate_relations_for_memory must not create duplicate relation JSON files if the relation already exists.
    """
    from memory.long_term import create_memory, create_relation, load_relations
    from memory.memory_relation import reevaluate_relations_for_memory

    existing_mem = create_memory(
        memory_type="decision",
        title="既存決定",
        content="既存方針",
    )
    existing_id = existing_mem.stem

    new_mem = create_memory(
        memory_type="decision",
        title="新規決定",
        content="新規方針",
    )
    new_id = new_mem.stem

    # Manually pre-create explicit relation
    create_relation(
        from_memory_id=new_id,
        relation="related",
        to_memory_id=existing_id,
    )

    initial_relations_count = len(load_relations())

    monkeypatch.setattr(
        "memory.memory_relation.find_memory_candidates",
        lambda title, content: [
            {"id": existing_id, "path": str(existing_mem), "content": "既存方針", "score": 10}
        ],
    )

    monkeypatch.setattr(
        "memory.memory_relation.analyze_memory_relations",
        lambda title, content, candidates: [
            {"id": existing_id, "relation": "related"}
        ],
    )

    created = reevaluate_relations_for_memory(
        memory_id=new_id,
        title="新規決定",
        content="新規方針",
    )

    assert created == []
    assert len(load_relations()) == initial_relations_count

