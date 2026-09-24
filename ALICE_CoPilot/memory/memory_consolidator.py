import json
import os
import secrets
import sqlite3
from pathlib import Path

import config
from memory.memory_extractor import extract_memories
from memory.memory_manager import process_memory


STATE_PATH = config.MEMORY_ROOT / "consolidation_state.json"


def consolidate_conversation(conversation: list[dict]) -> list[dict]:
    """
    会話から長期記憶候補を抽出し、
    既存のMemory Managerを通して保存する。

    長期記憶の確定根拠はユーザー発言とする。
    Assistantの発言は長期記憶抽出の根拠として使用しない。
    """

    # ユーザー発言が存在しない会話は記憶対象にしない。
    if not any(
        message.get("role") == "user"
        for message in conversation
    ):
        return []

    memories = extract_memories(conversation)

    results = []
    for memory in memories:
        content = memory.get("content")
        if not content:
            continue
        result = process_memory(content)
        results.append(result)
    return results


def load_last_processed_id() -> int:
    """
    前回処理したメッセージIDを取得する。
    """
    if not STATE_PATH.exists():
        return 0
    with STATE_PATH.open("r", encoding="utf-8") as f:
        state = json.load(f)
    return int(state.get("last_processed_message_id", 0))


def save_last_processed_id(message_id: int) -> None:
    """
    最後に正常処理したメッセージIDを保存する（アトミック書き込み）。
    """
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = STATE_PATH.with_name(f".{STATE_PATH.name}.tmp_{secrets.token_hex(4)}")
    try:
        tmp_path.write_text(
            json.dumps(
                {
                    "last_processed_message_id": message_id,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(str(tmp_path), str(STATE_PATH))
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        raise


def get_pending_messages() -> list[dict]:
    """
    前回のConsolidation以降に追加されたメッセージを取得する。
    """
    last_processed_id = load_last_processed_id()
    with sqlite3.connect(config.DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT
                id,
                timestamp,
                channel_id,
                user_id,
                role,
                content
            FROM messages
            WHERE id > ?
            ORDER BY id ASC
            """,
            (last_processed_id,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "timestamp": row[1],
            "channel_id": row[2],
            "user_id": row[3],
            "role": row[4],
            "content": row[5],
        }
        for row in rows
    ]


def consolidate_pending_messages(limit: int | None = None) -> list[dict]:
    """
    未処理の短期記憶を取得し、
    User発言を起点としてConsolidationする。

    各Consolidation単位は、
    「同一channelの直前のAssistant発言 + 現在のUser発言」
    で構成する。

    メッセージはDBのID順に処理する。
    channelごとの直前メッセージは独立して管理する。

    limit:
        ConsolidationするUserメッセージ数の上限。
        limit到達後のメッセージは処理済みとして扱わない。
    """

    messages = get_pending_messages()

    if not messages:
        return []

    results = []

    # Channelごとの直前メッセージ。
    #
    # 「直前Assistant」ではなく「直前Message」を保持する。
    # これにより、
    #
    # Assistant
    # User
    # User
    #
    # の2人目のUserに、最初のAssistantを
    # 再利用してしまうことを防ぐ。
    previous_message_by_channel = {}

    max_processed_id = None
    processed_user_count = 0

    for message in messages:
        channel_id = message["channel_id"]

        # User以外のメッセージ。
        if message["role"] != "user":
            previous_message_by_channel[channel_id] = message
            continue

        # limit到達後は、このUser以降を処理しない。
        #
        # したがって、このUserのIDを
        # processed stateへ含めてはいけない。
        if limit is not None and processed_user_count >= limit:
            break

        processed_user_count += 1

        previous_message = previous_message_by_channel.get(
            channel_id
        )

        # 明示的な「覚えておいて」は、
        # main.py側ですでにMemory保存されているため、
        # Consolidatorでは再処理しない。
        #
        # このUser自身が直前メッセージになるので、
        # 次のUserへAssistant contextを持ち越さない。
        if message["content"].startswith("覚えておいて"):
            previous_message_by_channel[channel_id] = message

            if max_processed_id is None or message["id"] > max_processed_id:
                max_processed_id = message["id"]

            continue

        conversation = []

        # 本当に「直前」がAssistantの場合だけ使用する。
        if (
            previous_message is not None
            and previous_message["role"] == "assistant"
        ):
            conversation.append(
                {
                    "role": "assistant",
                    "content": previous_message["content"],
                }
            )

        conversation.append(
            {
                "role": "user",
                "content": message["content"],
            }
        )

        results.extend(
            consolidate_conversation(conversation)
        )

        # 今回のUserを、そのchannelの直前メッセージとして保存。
        #
        # これが重要。
        #
        # Assistant
        # User
        # User
        #
        # の場合、2人目のUserに最初のAssistantを
        # 再利用させない。
        previous_message_by_channel[channel_id] = message

        if max_processed_id is None or message["id"] > max_processed_id:
            max_processed_id = message["id"]

    # 実際に処理したUserメッセージの最大IDまでを
    # 処理済みとして保存する。
    #
    # limitで途中停止した場合、
    # それより後ろのメッセージは次回Consolidationで再取得される。
    if max_processed_id is not None:
        save_last_processed_id(max_processed_id)

    return results