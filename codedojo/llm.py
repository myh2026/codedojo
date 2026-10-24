"""DeepSeek 客户端（OpenAI 兼容协议）。

默认教师 = `deepseek-flash`（服务端版本 DeepSeek-V4.1-Flash-1017），
可用环境变量 DEEPSEEK_MODEL 覆盖。

flash 要点（api-docs.deepseek.com，2026-10 核实）：
  - thinking 模式默认开启，reasoning 计入 max_tokens——生成调用给足预算；
  - 裁判/分类等短调用应关 thinking（thinking=False），省 token 提速；
  - 缓存命中输入价是 miss 的 1/50（$0.006/M vs $0.30/M）——稳定前缀
    （SYSTEM_PROMPT）天然吃缓存，成本账本按命中/未命中分别计价。
"""

import json
import os
import time
from typing import List, Optional

# 峰时价（USD / 百万 token）；谷时减半——账本按峰时保守估计
PRICE_IN_MISS = 0.30
PRICE_IN_HIT = 0.006
PRICE_OUT = 1.20

GEN_MAX_TOKENS = 16384   # reasoning 计入预算，给足防截断
JUDGE_MAX_TOKENS = 2048


def default_model() -> str:
    return os.environ.get("DEEPSEEK_MODEL", "deepseek-flash")


def estimate_cost_usd(tokens_in_miss: int, tokens_in_hit: int,
                      tokens_out: int) -> float:
    return (tokens_in_miss / 1e6 * PRICE_IN_MISS
            + tokens_in_hit / 1e6 * PRICE_IN_HIT
            + tokens_out / 1e6 * PRICE_OUT)


class LLM:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 base_url: str = "https://api.deepseek.com") -> None:
        self._api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self._model = model or default_model()
        self._base_url = base_url
        self._client = None
        self.calls = 0
        self.tokens_in_miss = 0
        self.tokens_in_hit = 0
        self.tokens_out = 0
        self.cost_usd = 0.0

    @property
    def ready(self) -> bool:
        return bool(self._api_key)

    @property
    def model(self) -> str:
        return self._model

    def _ensure(self):
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("缺少 DEEPSEEK_API_KEY")
            from openai import OpenAI
            self._client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        return self._client

    def _account(self, usage) -> None:
        if usage is None:
            return
        t_in = getattr(usage, "prompt_tokens", 0) or 0
        hit = getattr(usage, "prompt_cache_hit_tokens", 0) or 0  # DeepSeek 特有
        hit = min(hit, t_in)
        miss = t_in - hit
        t_out = getattr(usage, "completion_tokens", 0) or 0
        self.tokens_in_miss += miss
        self.tokens_in_hit += hit
        self.tokens_out += t_out
        self.cost_usd += estimate_cost_usd(miss, hit, t_out)

    def chat(self, messages: List[dict], json_mode: bool = False,
             temperature: float = 0.2, retries: int = 2,
             thinking: Optional[bool] = None,
             max_tokens: Optional[int] = None) -> Optional[str]:
        """对话；失败重试。thinking=None 走服务端默认（flash 默认开）。

        thinking 参数经 extra_body 传递；若 API 版本不认该参数则去掉重试
        一次（优雅降级，不因参数语法差异中断任务）。
        """
        client = self._ensure()
        kwargs = dict(model=self._model, messages=messages, temperature=temperature,
                      timeout=180,
                      max_tokens=max_tokens or GEN_MAX_TOKENS)
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if thinking is not None:
            kwargs["extra_body"] = {"thinking": {"type": "enabled" if thinking else "disabled"}}

        for attempt in range(retries + 1):
            try:
                self.calls += 1
                resp = client.chat.completions.create(**kwargs)
                self._account(getattr(resp, "usage", None))
                return resp.choices[0].message.content or ""
            except Exception as exc:
                # thinking 参数不被接受（旧网关/协议差异）→ 去参降级重试一次
                if "extra_body" in kwargs and attempt == 0:
                    kwargs.pop("extra_body", None)
                    continue
                if attempt >= retries:
                    raise
                time.sleep(2 * (attempt + 1))
        return None

    def chat_json(self, messages: List[dict], temperature: float = 0.2,
                  thinking: Optional[bool] = None,
                  max_tokens: Optional[int] = None) -> Optional[dict]:
        """要求 JSON 输出并解析；协议违规回喂一次。"""
        for _ in range(2):
            text = self.chat(messages, json_mode=True, temperature=temperature,
                             thinking=thinking, max_tokens=max_tokens)
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
        tokens_in = self.tokens_in_miss + self.tokens_in_hit
        return {"llm_calls": self.calls, "tokens_in": tokens_in,
                "tokens_out": self.tokens_out,
                "tokens_in_hit": self.tokens_in_hit,
                "cost_usd": round(self.cost_usd, 6)}
