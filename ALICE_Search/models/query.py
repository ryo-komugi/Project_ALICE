"""ALICE_Search 検索クエリモデル

Full Text Query と Metadata Filters を明確に分離して保持する。
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SearchQuery:
    """検索リクエストモデル

    1. Full Text Query (キーワード・自由文)
    2. Metadata Filters (属性による絞り込み)
    """

    # --- 1. Full Text Query ---
    query: str | None = None

    # --- 2. Metadata Filters ---
    user_id: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    workflow: str | None = None
    status: str | None = None
    module: list[str] | str | None = None

    # --- 3. Pagination & Options ---
    limit: int = 10
    offset: int = 0

    def get_modules(self) -> list[str] | None:
        """module をリスト形式で正規化して返す"""
        if self.module is None:
            return None
        if isinstance(self.module, str):
            return [self.module]
        return list(self.module)
