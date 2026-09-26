import copy
import json
from pathlib import Path


class DownloadFlex:
    def __init__(self):
        template = (Path(__file__).parent / "template" / "download.json")
        with open(template, "r", encoding="utf-8") as f:
            self.template = json.load(f)

    def create(self, title, filename, download_url=None, view_url=None, url=None):
        effective_download_url = download_url or url or ""
        effective_view_url = view_url or effective_download_url
        flex = copy.deepcopy(self.template)
        self.replace(flex, "${TITLE}", title)
        self.replace(flex, "${FILENAME}", filename)
        self.replace(flex, "${VIEW_URL}", effective_view_url)
        self.replace(flex, "${DOWNLOAD_URL}", effective_download_url)
        self.replace(flex, "${URL}", effective_download_url)
        return flex

    def create_bubble(self, title, filename, download_url=None, view_url=None, url=None):
        """単一のバブル辞書を生成して返す（カルーセル構築用）"""
        effective_download_url = download_url or url or ""
        effective_view_url = view_url or effective_download_url
        bubble = copy.deepcopy(self.template["contents"])
        self.replace(bubble, "${TITLE}", title)
        self.replace(bubble, "${FILENAME}", filename)
        self.replace(bubble, "${VIEW_URL}", effective_view_url)
        self.replace(bubble, "${DOWNLOAD_URL}", effective_download_url)
        self.replace(bubble, "${URL}", effective_download_url)
        return bubble

    def create_carousel(self, items: list[dict], alt_text: str = "成果物が届きました"):
        """複数アイテムからLINE Flexカルーセルメッセージを生成する"""
        bubbles = [
            self.create_bubble(
                title=item.get("title", ""),
                filename=item.get("filename", ""),
                download_url=item.get("download_url"),
                view_url=item.get("view_url"),
                url=item.get("url"),
            )
            for item in items
        ]
        return {
            "type": "flex",
            "altText": alt_text,
            "contents": {
                "type": "carousel",
                "contents": bubbles,
            },
        }

    def replace(self, obj, old, new):
        if isinstance(obj, dict):
            for key, value in obj.items():
                obj[key] = self.replace(value, old, new)
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                obj[i] = self.replace(value, old, new)
        elif isinstance(obj, str):
            return obj.replace(old, new)
        return obj
