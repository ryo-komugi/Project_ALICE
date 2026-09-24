"""
Ollama HTTP Client for ALICE_Minute.
Supports Ollama /api/chat with thinking separation, keep-alive control, and robust JSON extraction.
"""
import json
import logging
import re
import time
from typing import Any, Dict, Optional, Type, TypeVar
import requests
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class OllamaClient:
    def __init__(
        self,
        host: str,
        model: str,
        timeout: int = 900,
        fallback_model: Optional[str] = None,
    ):
        self.host = host.rstrip("/")
        self.model = model
        self.fallback_model = fallback_model
        self.timeout = timeout

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        num_ctx: int = 32768,
        format_json: bool = False,
        keep_alive: str = "5m",
        think: Optional[bool] = None,
        num_predict: Optional[int] = None,
    ) -> tuple[str, str]:
        """
        Ollama /api/chat を呼び出す。
        戻り値: (content, thinking)
        """
        url = f"{self.host}/api/chat"
        options: dict[str, Any] = {
            "temperature": temperature,
            "num_ctx": num_ctx,
        }
        if num_predict is not None:
            options["num_predict"] = num_predict

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
            "options": options,
        }
        if think is not None:
            payload["think"] = think
        if format_json:
            payload["format"] = "json"

        logger.info(
            f"[OllamaClient] Calling {url} (model={self.model}, num_ctx={num_ctx}, "
            f"format_json={format_json}, think={think}, num_predict={num_predict}, keep_alive={keep_alive})"
        )
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as e:
            if self.fallback_model and self.fallback_model != self.model:
                logger.warning(
                    f"[OllamaClient] Primary model '{self.model}' failed: {e}. "
                    f"Retrying with fallback '{self.fallback_model}'..."
                )
                payload["model"] = self.fallback_model
                resp = requests.post(url, json=payload, timeout=self.timeout)
                resp.raise_for_status()
            else:
                raise

        data = resp.json()
        message = data.get("message", {})
        content = message.get("content", "").strip()
        thinking = message.get("thinking", "").strip()

        # Clean any leaked <think> / <thought> tags from content
        for tag in ["think", "thought"]:
            open_tag = f"<{tag}>"
            if open_tag in content:
                tag_match = re.search(rf"<{tag}>(.*?)</{tag}>", content, flags=re.DOTALL)
                if tag_match:
                    if not thinking:
                        thinking = tag_match.group(1).strip()
                    content = re.sub(rf"<{tag}>.*?</{tag}>", "", content, flags=re.DOTALL).strip()

        return content, thinking

    def unload_model(self) -> None:
        """GPU VRAM を解放するため、keep_alive: 0 でアンロードする"""
        url = f"{self.host}/api/chat"
        models_to_unload = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models_to_unload.append(self.fallback_model)

        for m in set(models_to_unload):
            payload = {
                "model": m,
                "messages": [],
                "keep_alive": 0,
            }
            try:
                logger.info(f"[OllamaClient] Unloading model '{m}' from VRAM...")
                requests.post(url, json=payload, timeout=10)
                logger.info(f"[OllamaClient] Model '{m}' unload request sent successfully.")
            except Exception as e:
                logger.warning(f"[OllamaClient] Failed to unload model '{m}': {e}")

    @staticmethod
    def extract_json_object(raw_text: str) -> dict[str, Any]:
        """マークダウンコードブロックや余分なテキストから最も外側のJSONオブジェクトを抽出"""
        text = raw_text.strip()

        # 1. ```json ... ``` の抽出
        code_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        # 2. 最初と最後の { ... } を抽出
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_candidate = text[start : end + 1]
            try:
                return json.loads(json_candidate)
            except json.JSONDecodeError as e:
                logger.warning(f"[OllamaClient] Direct slice JSON parse failed: {e}")

        # 3. 直接パース
        return json.loads(text)

    def chat_structured(
        self,
        messages: list[dict[str, str]],
        schema_class: Type[T],
        temperature: float = 0.1,
        num_ctx: int = 32768,
        keep_alive: str = "5m",
        think: Optional[bool] = None,
        num_predict: Optional[int] = None,
    ) -> T:
        """JSON 出力を要求し、指定された Pydantic スキーマにパースして返す"""
        content, _ = self.chat(
            messages=messages,
            temperature=temperature,
            num_ctx=num_ctx,
            format_json=True,
            keep_alive=keep_alive,
            think=think,
            num_predict=num_predict,
        )
        json_dict = self.extract_json_object(content)

        if hasattr(schema_class, "model_validate"):
            return schema_class.model_validate(json_dict)
        return schema_class.parse_obj(json_dict)
