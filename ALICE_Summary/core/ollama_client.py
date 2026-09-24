import json
import re
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from dataclasses import dataclass


import logging

logger = logging.getLogger(__name__)


@dataclass
class OllamaResponse:
    content: str
    thinking: Optional[str]
    prompt_eval_count: int
    eval_count: int
    total_duration_sec: float
    load_duration_sec: float
    raw_response: Dict[str, Any]
    actual_model: str = ""


class OllamaClient:
    """Ollama API (/api/chat) との通信を担当するクライアント"""

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self.chat_url = f"{self.base_url}/api/chat"

    def _execute_request(
        self,
        model: str,
        messages: list[dict],
        format_json: bool,
        temperature: float,
        num_ctx: int,
        num_predict: int,
        repeat_penalty: float,
        timeout_sec: int,
        keep_alive: str | int,
    ) -> OllamaResponse:
        payload: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": keep_alive,
            "options": {
                "temperature": temperature,
                "num_ctx": num_ctx,
                "num_predict": num_predict,
                "repeat_penalty": repeat_penalty,
            },
        }

        if format_json:
            payload["format"] = "json"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            self.chat_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        elapsed = time.time() - t0

        message = resp_data.get("message", {})
        content = message.get("content", "")
        thinking = message.get("thinking", None)

        # 思考モデル（Thinking Model）のタグ混入対策
        if "<think>" in content and "</think>" in content:
            think_match = re.search(r"<think>(.*?)</think>", content, flags=re.DOTALL)
            if think_match:
                if not thinking:
                    thinking = think_match.group(1).strip()
                content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()

        prompt_eval_count = resp_data.get("prompt_eval_count", 0)
        eval_count = resp_data.get("eval_count", 0)
        total_duration = resp_data.get("total_duration", 0) / 1e9 or elapsed
        load_duration = resp_data.get("load_duration", 0) / 1e9

        return OllamaResponse(
            content=content,
            thinking=thinking,
            prompt_eval_count=prompt_eval_count,
            eval_count=eval_count,
            total_duration_sec=total_duration,
            load_duration_sec=load_duration,
            raw_response=resp_data,
            actual_model=model,
        )

    def chat(
        self,
        model: str,
        messages: list[dict],
        format_json: bool = False,
        temperature: float = 0.2,
        num_ctx: int = 32768,
        num_predict: int = 4096,
        repeat_penalty: float = 1.1,
        timeout_sec: int = 600,
        keep_alive: str | int = "5m",
        max_retries: int = 3,
        retry_delay: float = 2.0,
        backoff_factor: float = 2.0,
        fallback_model: Optional[str] = None,
    ) -> OllamaResponse:
        """Ollama /api/chat を呼び出す（リトライ＆フォールバック付き）"""
        candidate_models = [model]
        if fallback_model and fallback_model != model:
            candidate_models.append(fallback_model)

        last_error = None

        for model_idx, target_model in enumerate(candidate_models):
            is_fallback = model_idx > 0
            if is_fallback:
                logger.warning(
                    f"[OllamaClient] Falling back from primary model '{model}' to '{target_model}'..."
                )

            current_delay = retry_delay
            for attempt in range(1, max_retries + 1):
                try:
                    return self._execute_request(
                        model=target_model,
                        messages=messages,
                        format_json=format_json,
                        temperature=temperature,
                        num_ctx=num_ctx,
                        num_predict=num_predict,
                        repeat_penalty=repeat_penalty,
                        timeout_sec=timeout_sec,
                        keep_alive=keep_alive,
                    )
                except urllib.error.HTTPError as e:
                    last_error = e
                    # 404 (Model not found) の場合は同一モデルのリトライをスキップしてフォールバックへ
                    if e.code == 404:
                        logger.error(
                            f"[OllamaClient] Model '{target_model}' not found (HTTP 404)."
                        )
                        break
                    logger.warning(
                        f"[OllamaClient] HTTP {e.code} on model '{target_model}' (attempt {attempt}/{max_retries}): {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )
                except (urllib.error.URLError, TimeoutError, ConnectionError, Exception) as e:
                    last_error = e
                    logger.warning(
                        f"[OllamaClient] Request error on model '{target_model}' (attempt {attempt}/{max_retries}): {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )

                if attempt < max_retries:
                    time.sleep(current_delay)
                    current_delay *= backoff_factor

        # すべてのモデル・試行が失敗
        raise RuntimeError(
            f"Ollama request failed after trying models {candidate_models} with retries: {last_error}"
        )

    def unload_model(self, model: str) -> None:
        """keep_alive: 0 でダミーリクエストを送り、モデルをVRAMから解放する"""
        try:
            payload = {
                "model": model,
                "messages": [],
                "keep_alive": 0,
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                self.chat_url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception:
            pass

    @staticmethod
    def extract_json_object(text: str) -> Dict[str, Any]:
        """LLMの出力文字列から確実にJSONオブジェクトを取り出す"""
        text = text.strip()

        # 思考ブロック（<thought>...</thought> 等）があれば除去
        text = re.sub(r"<thought>[\s\S]*?</thought>", "", text).strip()
        text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

        def clean_and_load(s: str) -> Optional[Dict[str, Any]]:
            s = s.strip()
            # 1. strict=False で直接試行
            try:
                res = json.loads(s, strict=False)
                if isinstance(res, dict):
                    return res
            except Exception:
                pass

            # 2. 末尾の余分なカンマ（trailing commas）を除去
            cleaned = re.sub(r",\s*([\]}])", r"\1", s)
            try:
                res = json.loads(cleaned, strict=False)
                if isinstance(res, dict):
                    return res
            except Exception:
                pass

            # 3. カッコの欠落修復試行
            for suffix in ["}", "]}", "]}}", "]}}}", "\"}]}", "}\n}"]:
                try:
                    res = json.loads(cleaned + suffix, strict=False)
                    if isinstance(res, dict):
                        return res
                except Exception:
                    pass

            return None

        # 1. そのままパース
        res = clean_and_load(text)
        if res is not None:
            return res

        # 2. ```json ... ``` コードブロックを抽出
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            res = clean_and_load(match.group(1))
            if res is not None:
                return res

        # 3. 最初の '{' から最後の '}' までを抽出
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            candidate = text[first_brace : last_brace + 1]
            res = clean_and_load(candidate)
            if res is not None:
                return res

        # 4. 最初の '{' から末尾までを抽出して修復
        if first_brace != -1:
            candidate = text[first_brace:]
            res = clean_and_load(candidate)
            if res is not None:
                return res

        raise ValueError(f"Could not parse valid JSON from LLM output:\n{text[:500]}...")
