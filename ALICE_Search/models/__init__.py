"""ALICE_Search データモデルパッケージ"""
from .query import SearchQuery
from .result import SearchHit, SearchResult

__all__ = ["SearchQuery", "SearchHit", "SearchResult"]
