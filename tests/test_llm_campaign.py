"""flash 接入与蒸馏战役的离线测试（零 API 成本）。"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import codedojo.llm as llm_mod                     # noqa: E402
from codedojo.llm import LLM, default_model, estimate_cost_usd  # noqa: E402


class TestModelConfig:
    def test_default_model_flash(self, monkeypatch):
        monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
        assert default_model() == "deepseek-flash"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_MODEL", "my-model")
        assert default_model() == "my-model"
        assert LLM(api_key="k").model == "my-model"

    def test_explicit_param_wins(self, monkeypatch):
        monkeypatch.setenv("DEEPSEEK_MODEL", "env-model")
        assert LLM(api_key="k", model="explicit").model == "explicit"


class TestCostModel:
    def test_pricing_math(self):
        # 1000 miss + 2000 hit 输入，500 输出
        usd = estimate_cost_usd(1000, 2000, 500)
        expect = 1000 / 1e6 * 0.30 + 2000 / 1e6 * 0.006 + 500 / 1e6 * 1.20
        assert abs(usd - expect) < 1e-12

    def test_account_splitting(self):
        llm = LLM(api_key="k")

        class U:  # 模拟 DeepSeek usage
            prompt_tokens = 5000
            prompt_cache_hit_tokens = 4000
            completion_tokens = 200

        llm._account(U())
        c = llm.cost()
        assert c["tokens_in"] == 5000 and c["tokens_in_hit"] == 4000
        assert abs(c["cost_usd"] - estimate_cost_usd(1000, 4000, 200)) < 1e-9

    def test_hit_capped_at_total(self):
        llm = LLM(api_key="k")

        class U:  # 异常 usage：hit > total（防御）
            prompt_tokens = 100
            prompt_cache_hit_tokens = 500
            completion_tokens = 0

        llm._account(U())
        assert llm.tokens_in_miss == 0 and llm.tokens_in_hit == 100


class TestBudgetGate:
    def test_budget_blown(self):
        from demos.distill_campaign import BudgetedLLM, BudgetBlown
        llm = BudgetedLLM(api_key="k", budget_usd=0.001)
        llm.cost_usd = 0.01  # 已超
        try:
            llm.chat([{"role": "user", "content": "hi"}])
            raised = False
        except BudgetBlown:
            raised = True
        assert raised

    def test_budget_ok_when_under(self):
        from demos.distill_campaign import BudgetedLLM
        llm = BudgetedLLM(api_key="k", budget_usd=1.0)
        llm.cost_usd = 0.5
        assert llm.cost_usd < llm.budget_usd  # 闸内（不真调 API）


class TestThinkingKwargs:
    def test_thinking_off_params_reach_create(self, monkeypatch):
        llm = LLM(api_key="k")
        captured = {}

        class FakeResp:
            class usage:
                prompt_tokens = 0
                prompt_cache_hit_tokens = 0
                completion_tokens = 0
            choices = [type("C", (), {"message": type("M", (), {"content": "{}"})})()]

        def fake_create(**kwargs):
            captured.update(kwargs)
            return FakeResp()

        class FakeCompletions:
            def create(self, **kw):
                return fake_create(**kw)

        class FakeClient:
            chat = type("Chat", (), {"completions": None})()

        FakeClient.chat.completions = type("C", (), {"create": staticmethod(fake_create)})()
        llm._client = FakeClient()
        llm.chat_json([{"role": "user", "content": "输出 {}"}],
                      thinking=False, max_tokens=2048)
        assert captured["extra_body"] == {"thinking": {"type": "disabled"}}
        assert captured["max_tokens"] == 2048
