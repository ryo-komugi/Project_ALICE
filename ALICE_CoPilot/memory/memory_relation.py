import json
from pathlib import Path
import requests
import config
from memory.memory_search import search_memories
from memory.memory_subject import filter_memories_by_subject
from memory.long_term import (
    create_relation,
    find_superseded_memory_ids,
    load_relations,
)


MEMORY_ROOT = config.MEMORY_ROOT
OLLAMA_URL = config.OLLAMA_URL
OLLAMA_MODEL = config.OLLAMA_MODEL


def _memory_timestamp(memory_id: str) -> str:
    """
    Extract the timestamp prefix from a Memory ID.

    Memory ID format:
        YYYYMMDD_HHMMSS_microseconds_Title
    """
    if not memory_id:
        return ""

    parts = memory_id.split("_", 3)

    if len(parts) < 3:
        return ""

    return "_".join(parts[:3])


def find_memory_candidates(title: str, content: str, limit: int = 10) -> list[dict]:
    """
    Find existing Markdown memories that may be related
    to the new memory using the long-term memory search.
    """

    query = f"{title}\n{content}"

    results = search_memories(query=query, limit=limit)

    return [
        {
            "id": item["id"],
            "path": item["path"],
            "content": item["content"],
            "score": item["score"],
        }
        for item in results
    ]


def analyze_memory_relations(title: str, content: str, candidates: list[dict]) -> list[dict]:
    """
    Analyze relationships between a new memory and existing candidates.

    Supported relations:
        related
        supersedes
        conflicts

    This function never modifies files.
    """
    candidates = filter_memories_by_subject(
        title=title,
        content=content,
        candidates=candidates,
    )

    if not candidates:
        return []

    # ---------------------------------------------------------
    # Determine Current / Historical status from Relations.
    #
    # Memory itself is immutable.
    # Therefore, Current/Historical status is derived from
    # the immutable Relation graph.
    #
    # Relation direction:
    #
    #     new Memory
    #         --supersedes-->
    #     old Memory
    #
    # A Memory appearing on the `to` side of a supersedes
    # Relation is Historical.
    #
    # A Memory that is not superseded is a Current candidate.
    #
    # This decision is deterministic and must not be delegated
    # to the LLM.
    # ---------------------------------------------------------

    superseded_ids = find_superseded_memory_ids()

    current_candidate_ids = {
        item["id"]
        for item in candidates
        if item["id"] not in superseded_ids
    }
    # ---------------------------------------------------------
    # Determine the newest Current Memory.
    #
    # supersedes represents a direct update relationship.
    # Therefore, only the newest Current Memory is eligible
    # to become the direct supersedes target.
    # ---------------------------------------------------------

    current_candidates = [
        item
        for item in candidates
        if item["id"] in current_candidate_ids
    ]

    if current_candidates:
        supersedes_candidate = max(
            current_candidates,
            key=lambda item: _memory_timestamp(item["id"]),
        )
        supersedes_candidate_id = supersedes_candidate["id"]
    else:
        supersedes_candidate_id = None
        
    candidate_text = "\n\n".join(
        (
            f"Candidate {index}\n"
            f"Memory ID: {item['id']}\n"
            f"検索スコア: {item['score']}\n"
            f"状態: "
            f"{'Current Memory' if item['id'] in current_candidate_ids else 'Historical Memory'}\n"
            f"{item['content']}"
        )
        for index, item in enumerate(candidates, 1)
    )

    prompt = f"""
新しい長期記憶があります。

タイトル:
{title}

内容:
{content}

以下は既存の長期記憶です。

{candidate_text}

新しいMemoryと既存Memoryの関係を判定してください。

【関係の種類】

related:
内容上直接関係しているが、
更新・置換・矛盾の関係ではない。

supersedes:
新しいMemoryの内容が、
既存Memoryの事実・方針・決定などを
直接更新または置き換えている。

重要:
supersedesは、候補一覧で
「Current Memory」と表示されているMemoryに対してのみ使用してください。

「Historical Memory」と表示されているMemoryには
supersedesを指定してはいけません。

Historical Memoryは、過去に別のMemoryによって
supersedesされたMemoryです。

新しいMemoryがHistorical Memoryの内容を
さらに更新しているように見える場合でも、
そのHistorical Memoryを直接supersedesしてはいけません。

必ず現在有効なCurrent Memoryを対象としてください。

Current Memoryが複数存在し、新しいMemoryが
複数のCurrent Memoryを直接更新・置換する場合は、
複数のsupersedesを返して構いません。

一方、Current Memoryであっても、
新しいMemoryがその内容を直接更新・置換していない場合は
supersedesにしてはいけません。

supersedes対象の選択は、
候補一覧のCandidate番号をそのまま使用してください。

【supersedes と conflicts の優先判定】

両者の内容が互いに両立しない場合は、まず
「新しいMemoryが既存Memoryを明示的に更新・変更・改定・置換しているか」
を確認してください。

新しいMemoryに、
「変更された」
「変更する」
「改定された」
「改定する」
「新方針」
「新しい方針」
「置き換える」
「廃止して」
など、既存Memoryを更新・置換することを明示する表現がある場合は
supersedesと判定してください。

一方、単に既存Memoryと反対・両立不能な内容を述べているだけで、
既存Memoryを更新・置換することが明示されていない場合は
conflictsと判定してください。

重要:
「新しいMemoryの方が新しい」という時間的な理由だけで
supersedesと判定してはいけません。

例えば、

既存:
「監査ログの保存を必須とする。」

新:
「監査ログの保存を禁止する。」

これは両立しないが、新しいMemoryが既存Memoryを
明示的に更新・置換したとは書かれていないため、
conflictsです。

一方、

既存:
「通知方式はメールを使用する。」

新:
「通知方式をDiscordに変更する。」

これは新しいMemoryが既存Memoryを明示的に変更しているため、
supersedesです。

例えば、

既存Memory:
「ALICE_CoPilotのテスト環境ではログ保存を必須とする。」

新しいMemory:
「ALICE_CoPilotのテスト環境ではログ保存を禁止する。」

この場合、両方を同時に正しいものとして扱うことができないため、
conflictsと判定してください。

一方、

既存Memory:
「旧方針としてメール通知を使用する。」

新しいMemory:
「新方針としてDiscord通知へ変更する。」

のように、新しいMemoryが明確に既存Memoryを更新・置換している場合は、
supersedesと判定してください。

【重要】

- 単に同じプロジェクトやテーマに属するだけなら
  relatedにしないでください。
- 関係がないMemoryは結果に含めないでください。
- supersedesは、新しいMemoryが既存Memoryを
  実質的に更新・置換している場合だけ使用してください。
- 単なる関連情報をsupersedesにしないでください。
- 判断できない場合は無理に関係を付けないでください。
- 1つの既存Memoryに対して、最も適切な関係を
  1種類だけ選んでください。

【Candidate番号に関する重要なルール】

関係を返す場合は、候補一覧に記載された
Candidate番号を使用してください。

- Candidate番号を変更してはいけません。
- Candidate番号を生成してはいけません。
- 候補一覧に存在しないCandidate番号を返してはいけません。
- Memory IDは返さないでください。

必ず候補一覧のCandidate番号をそのまま使用してください。

必ずJSONだけを返してください。

形式:

{{
    "relations": [
        {{
            "candidate": 1,
            "relation": "related"
        }},
        {{
            "candidate": 2,
            "relation": "supersedes"
        }}
    ]
}}

関係するMemoryが存在しない場合:

{{
    "relations": []
}}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "あなたはALICE_CoPilotの"
                        "Memory関係分析エンジンです。"
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
            "options": {
                "num_ctx": config.OLLAMA_CONTEXT,
            },
        },
        timeout=300,
    )

    response.raise_for_status()

    print(
        f"[MEMORY RELATION ANALYSIS HTTP] "
        f"{response.status_code}"
    )
    print(
        f"[MEMORY RELATION ANALYSIS RAW] "
        f"{response.text!r}"
    )

    data = response.json()

    try:
        result = json.loads(data["message"]["content"])
    except (json.JSONDecodeError, TypeError) as e:
        print(
            f"[MEMORY RELATION ANALYSIS ERROR] "
            f"Invalid JSON response: {e}"
        )
        print(
            f"[MEMORY RELATION ANALYSIS RESPONSE] "
            f"{data['message']['content']!r}"
        )
        return []

    relations = result.get("relations", [])

    if not isinstance(relations, list):
        return []

    valid_relations = {"related", "supersedes", "conflicts"}

    validated = []

    for item in relations:
        if not isinstance(item, dict):
            continue

        candidate_number = item.get("candidate")
        relation = item.get("relation")

        if not isinstance(candidate_number, int):
            continue

        if candidate_number < 1 or candidate_number > len(candidates):
            continue

        if relation not in valid_relations:
            continue

        memory_id = candidates[candidate_number - 1]["id"]

        # -----------------------------------------------------
        # supersedes validation
        #
        # The LLM determines whether a supersedes relationship
        # exists, but the code determines the actual target.
        #
        # Only the newest Current Memory may be directly
        # superseded.
        #
        # Historical Memories must never become direct
        # supersedes targets.
        #
        # The LLM's candidate number is not trusted as the
        # supersedes target.
        # -----------------------------------------------------
        if relation == "supersedes":

            if supersedes_candidate_id not in current_candidate_ids:
                continue

            if any(
                item["relation"] == "supersedes"
                for item in validated
            ):
                continue

            validated.append(
                {
                    "id": supersedes_candidate_id,
                    "relation": "supersedes",
                }
            )

            continue

        validated.append(
            {
                "id": memory_id,
                "relation": relation,
            }
        )

    return validated


def find_duplicate_memory(title: str, content: str, limit: int = 10, candidates: list[dict] | None = None) -> str | None:
    """
    Find an existing memory that represents the same fact,
    decision, policy, or information as the new memory.

    Related memories are not considered duplicates.
    Only substantially identical memories should be returned.

    candidates:
        Optional pre-filtered candidate memories.
        When provided, no additional memory search is performed.
    """

    if candidates is None:
        candidates = find_memory_candidates(title=title, content=content, limit=limit)
    if not candidates:
        return None

    candidates = filter_memories_by_subject(title=title, content=content, candidates=candidates)
    if not candidates:
        return None

    candidate_text = "\n\n".join(
        f"ID: {item['id']}\n"
        f"検索スコア: {item['score']}\n"
        f"{item['content']}"
        for item in candidates
    )

    prompt = f"""
新しい長期記憶があります。

タイトル:
{title}

内容:
{content}

以下は既存の長期記憶です。

{candidate_text}

この中に、新しい長期記憶と
「実質的に同一の内容」を表している既存記憶があるか判断してください。

【Duplicateの定義】

Duplicateとは、

「新しいMemoryを保存しなくても、
既存Memoryだけで新しいMemoryが表している
事実・決定・方針・仕様・知識を同じ意味で表現できる状態」

を指します。

単に同じテーマ・プロジェクト・対象について述べているだけでは
Duplicateではありません。

【Duplicateと判定する場合】

以下の場合はDuplicateです。

- 同じ事実を別の表現で記述している
- 同じ決定事項を別の表現で記述している
- 同じ方針を別の表現で記述している
- 同じ仕様を別の表現で記述している
- 同じ知識・情報を要約・言い換えしただけである
- 表現やタイトルが異なっていても、実質的に同じ内容である
- 新しいMemoryを追加しても、既存Memoryが表す情報量・意味・状態が実質的に増えない

【Duplicateではない場合】

以下の場合はDuplicateではありません。

- 単に関連しているだけ
- 同じプロジェクトに関する別の情報
- 同じテーマだが内容が異なる
- より具体的な別の決定・仕様・知識である
- 新しいMemoryによって新しい事実・状態・決定・方針・仕様が追加される
- 既存Memoryの内容を更新・変更・改定・廃止・置換している
- 既存Memoryでは成立していた方針・仕様・決定を、新しい内容へ変更している
- 既存Memoryとは異なる状態を表している
- 既存Memoryと両立しない新しい内容を表している
- 新しいMemoryが既存Memoryを明示的に更新する内容である

【特に重要：更新・変更】

新しいMemoryが既存Memoryの内容を

- 変更する
- 更新する
- 改定する
- 廃止する
- 置き換える
- 新しい方式へ移行する

など、既存Memoryとは異なる新しい状態を明示している場合、
Duplicateではありません。

例えば、

既存:
「通知方式はメールを使用する。」

新規:
「通知方式をDiscordに変更する。」

この場合、新規Memoryは既存Memoryの単なる言い換えではなく、
既存Memoryとは異なる新しい状態を表しています。

したがってDuplicateではありません。

【重要：同じ対象でも状態が変わればDuplicateではない】

例えば、

既存:
「方式Aを使用する。」

新規:
「方式Aを廃止し、方式Bへ変更する。」

この場合、新規Memoryは既存Memoryと同じ内容を表していません。

新規Memoryは方式Aから方式Bへの状態変更を表しているため、
Duplicateではありません。

一方、

既存:
「方式Aを使用する。」

新規:
「方式Aを採用している。」

この場合は同じ状態・同じ事実を別の表現で記述しているため、
Duplicateです。

【DuplicateとRelationの関係】

Duplicate判定では、
「既存Memoryとの関係がrelated / supersedes / conflictsのどれか」
を判定する必要はありません。

ここで判断するのは、
「新しいMemoryを別途保存する必要があるか」
だけです。

新しいMemoryが既存Memoryと実質的に同一ならDuplicateです。

新しいMemoryが既存Memoryとは異なる新しい状態・事実・決定・方針・仕様を表しているなら、
Duplicateではありません。

その場合のrelated / supersedes / conflictsの判断は、
後段のMemory Relation Analysisで行います。

【判断に迷う場合】

単に関連しているだけならDuplicateではありません。

一方、既存Memoryだけで新しいMemoryの内容を
同じ意味で完全に表現できる場合はDuplicateです。

新しい事実・状態・決定・方針・仕様が追加されている場合は、
Duplicateではありません。

必ず新しいMemoryと既存Memoryの
「意味」「状態」「決定内容」を比較してください。

タイトルや共通する単語だけを根拠にDuplicateと判定してはいけません。

必ず内容そのものを比較してください。

実質的に同一の既存記憶が存在する場合、
その既存記憶のIDを1件だけ返してください。

重複する既存記憶が存在しない場合は、
nullを返してください。

【IDに関する重要なルール】

返すIDは候補一覧に記載されているIDを
完全にそのままコピーしてください。

- IDを短縮してはいけません。
- IDの一部だけを返してはいけません。
- IDを変更してはいけません。
- IDを生成してはいけません。
- 候補一覧に存在しないIDを返してはいけません。

必ずJSONだけを返してください。

形式:

{{
"duplicate": "既存記憶のID"
}}

または

{{
"duplicate": null
}}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "あなたはALICE_CoPilotの"
                        "記憶重複判定エンジンです。"
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "stream": False,
            "format": "json",
            "think": False,
            "keep_alive": config.OLLAMA_KEEP_ALIVE,
            "options": {
                "num_ctx": config.OLLAMA_CONTEXT,
            },
        },
        timeout=300,
    )

    response.raise_for_status()

    print(
        f"[MEMORY DUPLICATE HTTP] "
        f"{response.status_code}"
    )
    print(
        f"[MEMORY DUPLICATE RAW] "
        f"{response.text!r}"
    )

    data = response.json()

    try:
        result = json.loads(data["message"]["content"])
    except (json.JSONDecodeError, TypeError) as e:
        print(
            f"[MEMORY DUPLICATE ERROR] "
            f"Invalid JSON response: {e}"
        )
        print(
            f"[MEMORY DUPLICATE RESPONSE] "
            f"{data['message']['content']!r}"
        )
        return None

    duplicate_id = result.get("duplicate")

    if duplicate_id is None:
        return None

    valid_ids = {
        item["id"]
        for item in candidates
    }

    if duplicate_id not in valid_ids:
        return None

    return duplicate_id


def reevaluate_relations_for_memory(
    memory_id: str,
    title: str,
    content: str,
    candidates: list[dict] | None = None,
    exclude_ids: set[str] | list[str] | None = None,
    analyze_fn=None,
    create_rel_fn=None,
) -> list[dict]:
    """
    Common entry point to re-evaluate and save relations for a saved memory
    against existing memories in the store.

    Args:
        memory_id: The ID (filename stem) of the target memory.
        title: Title of the target memory.
        content: Content of the target memory.
        candidates: Optional pre-fetched candidate list. If None, find_memory_candidates is called.
        exclude_ids: Optional collection of memory IDs to exclude from candidates (e.g. same batch IDs).
        analyze_fn: Optional custom function for relation analysis (defaults to analyze_memory_relations).
        create_rel_fn: Optional custom function for relation creation (defaults to create_relation).

    Returns:
        List of created relation dictionaries, each containing:
            "relation": relation type ("related", "supersedes", "conflicts"),
            "memory_id": target memory ID,
            "path": Path object or str of created relation file.
    """
    if not memory_id:
        return []

    if analyze_fn is None:
        analyze_fn = analyze_memory_relations

    if create_rel_fn is None:
        create_rel_fn = create_relation

    exclude = set(exclude_ids or [])
    exclude.add(memory_id)

    if candidates is None:
        candidates = find_memory_candidates(title=title, content=content)

    filtered_candidates = [
        item for item in candidates if item["id"] not in exclude
    ]

    if not filtered_candidates:
        return []

    relations = analyze_fn(
        title=title, content=content, candidates=filtered_candidates
    )

    if not relations:
        return []

    existing_relations = load_relations()
    existing_pairs = {
        (r.get("from"), r.get("relation"), r.get("to"))
        for r in existing_relations
    }

    created_relations = []
    for item in relations:
        rel_type = item["relation"]
        target_id = item["id"]
        pair = (memory_id, rel_type, target_id)

        if pair in existing_pairs:
            continue

        try:
            rel_path = create_rel_fn(
                from_memory_id=memory_id,
                relation=rel_type,
                to_memory_id=target_id,
            )
            existing_pairs.add(pair)
            created_relations.append(
                {
                    "relation": rel_type,
                    "memory_id": target_id,
                    "path": rel_path,
                }
            )
        except Exception as e:
            print(
                f"[MEMORY RELATION ERROR] Failed to create relation "
                f"{memory_id} --{rel_type}--> {target_id}: {e}"
            )

    return created_relations