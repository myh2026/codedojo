"""DeepSeek 客户端（OpenAI 兼容协议）。"""

import json
import os
import time
from typing import List, Optional


class LLM:
    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat",
                 base_url: str = "https://api.deepseek.com") -> None:
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self._model = model
        self._base_url = base_url
        self._client = None
        self.calls = 0
        self.tokens_in = 0
        self.tokens_out = 0

    @property
    def ready(self) -> bool:
        return bool(self._api_key)

    def _ensure(self):
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("缺少 DEEPSEEK_API_KEY")
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def chat(self, messages: List[dict], json_mode: bool = False,
             temperature: float = 0.2, retries: int = 2) -> Optional[str]:
        """对话；失败重试。返回文本或 None。"""
        client = self._ensure()
        kwargs = dict(model=self._model, messages=messages, temperature=temperature,
                      timeout=90)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        for attempt in range(retries + 1):
            try:
                self.calls += 1
                resp = client.chat.completions.create(**kwargs)
                usage = getattr(resp, "usage", None)
                self.tokens_in += getattr(usage, "prompt_tokens", 0) or 0
                self.tokens_out += getattr(usage, "completion_tokens", 0) or 0
                return resp.choices[0].message.content or ""
            except Exception as exc:
                if attempt >= retries:
                    raise
                time.sleep(2 * (attempt + 1))
        return None

    def chat_json(self, messages: List[dict], temperature: float = 0.2) -> Optional[dict]:
        """要求 JSON 输出并解析；协议违规回喂一次。"""
        for _ in range(2):
            text = self.chat(messages, json_mode=True, temperature=temperature)
            if not text:
                return None
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user", "content": "输出不是合法 JSON 对象，请重新输出恰好一个 JSON 对象。"},
                ]
        return None

    def cost(self) -> dict:
        return {"llm_calls": self.calls, "tokens_in": self.tokens_in,
                "tokens_out": self.tokens_out}
