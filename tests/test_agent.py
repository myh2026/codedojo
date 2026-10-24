"""CodeDojo 离线测试：MockLLM 下的完整闭环（无 API key 依赖）。"""

import json
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from codedojo.agent import Agent, TaskResult          # noqa: E402
from codedojo.llm import LLM                          # noqa: E402
from codedojo.sandbox import Sandbox                  # noqa: E402
from codedojo.skills import SkillStore, tokenize      # noqa: E402

GOOD_SOLUTION = {
    "plan": "实现词频统计并测试",
    "files": [
        {"path": "wordcount.py",
         "content": "def word_freq(text):\n    words = text.lower().split()\n    out = {}\n    for w in words:\n        out[w] = out.get(w, 0) + 1\n    return out\n"},
        {"path": "tests/test_wordcount.py",
         "content": "from wordcount import word_freq\n\ndef test_basic():\n    assert word_freq('a b a') == {'a': 2, 'b': 1}\n\ndef test_case():\n    assert word_freq('A a') == {'a': 2}\n"},
    ],
    "test_cmd": "python -m pytest -q",
}

BAD_THEN_GOOD = [
    {"plan": "先给错误实现",
     "files": [
         {"path": "calc.py", "content": "def add(a, b):\n    return a - b\n"},
         {"path": "tests/test_calc.py",
          "content": "from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"},
     ],
     "test_cmd": "python -m pytest -q"},
    GOOD_SOLUTION,
]


class MockLLM(LLM):
    """离线假教师：按脚本返回 JSON。"""

    def __init__(self, script):
        super().__init__(api_key="mock-key")
        self.script = list(script)
        self.calls = 0
        self.gen_calls = 0
        self.judge_calls = 0
        self.judge_verdict = True   # 裁判默认放行；测试可改 False 验证拦截

    def chat_json(self, messages, temperature=0.2):
        self.calls += 1
        self.tokens_in += 100
        self.tokens_out += 100
        # 裁判调用：自动应答，不消耗生成脚本
        if "能力裁判" in (messages[0]["content"] if messages else ""):
            self.judge_calls += 1
            return {"relevant": self.judge_verdict, "reason": "mock"}
        self.gen_calls += 1
        if not self.script:
            return None
        item = self.script.pop(0)
        return item if isinstance(item, dict) else json.loads(item)


@pytest.fixture
def tmp_store(tmp_path, monkeypatch):
    monkeypatch.setattr("codedojo.skills.STORE", tmp_path / "skills.json")
    monkeypatch.setattr("codedojo.hsl_bridge.CONTRACT_DIR", tmp_path / "contracts")
    return SkillStore(tmp_path / "skills.json")


def test_sandbox_run(tmp_path):
    sb = Sandbox("unit_test_sb")
    try:
        sb.write_files([{"path": "a.py", "content": "print('hi')\n"}])
        r = sb.run("python a.py")
        assert r["ok"] and "hi" in r["stdout"]
        bad = sb.run("python missing.py")
        assert not bad["ok"]
    finally:
        sb.cleanup()
    assert not sb.dir.exists()


def test_sandbox_rejects_escape(tmp_path):
    sb = Sandbox("unit_escape")
    try:
        with pytest.raises(ValueError):
            sb.write_files([{"path": "../evil.py", "content": "x"}])
    finally:
        sb.cleanup()


def test_tokenize_mixed():
    t = tokenize("写一个 word_count 函数统计词频")
    assert "word_count" in t
    assert any(len(x) == 2 for x in t if all("\u4e00" <= c <= "\u9fff" for c in x))


def test_skill_mount_and_match(tmp_store):
    tmp_store.mount("写一个函数统计文本词频", GOOD_SOLUTION["files"], "python -m pytest -q")
    hit = tmp_store.match("统计文本词频的函数")
    assert hit is not None
    miss = tmp_store.match("配置 nginx 反向代理")
    assert miss is None


def test_skill_retires_after_fails(tmp_store):
    s = tmp_store.mount("某个任务", GOOD_SOLUTION["files"], "python -m pytest -q")
    for _ in range(3):
        s.record(False)
    tmp_store.save()
    store2 = SkillStore(tmp_store.path)
    assert store2.skills[s.id].retired
    assert store2.match("某个任务") is None


def test_agent_llm_success_mounts_skill(tmp_store, monkeypatch):
    monkeypatch.setattr("codedojo.agent.MAX_FIX_ITERATIONS", 3)
    llm = MockLLM([GOOD_SOLUTION])
    agent = Agent(llm, tmp_store)
    r = agent.run_task("写一个函数统计文本词频，附带测试")
    assert r.ok and r.source == "llm"
    assert r.iterations == 1
    assert tmp_store.stats()["active"] == 1


def test_agent_fix_loop_recovers(tmp_store):
    llm = MockLLM(BAD_THEN_GOOD[:1] + [GOOD_SOLUTION])
    # 第一份坏实现（add 错），第二份是词频方案（测试针对词频）——注意测试文件不同，
    # 直接给修复后的 calc 版本更贴近真实：
    fixed_calc = {
        "plan": "修复 add",
        "files": [
            {"path": "calc.py", "content": "def add(a, b):\n    return a + b\n"},
            {"path": "tests/test_calc.py",
             "content": "from calc import add\n\ndef test_add():\n    assert add(1, 2) == 3\n"},
        ],
        "test_cmd": "python -m pytest -q",
    }
    llm = MockLLM([BAD_THEN_GOOD[0], fixed_calc])
    agent = Agent(llm, tmp_store)
    r = agent.run_task("写一个 add 函数返回两数之和，附带测试")
    assert r.ok and r.iterations == 2
    assert "修复" in r.plan or r.iterations == 2


def test_agent_skill_takeover_zero_llm(tmp_store):
    """核心主张：技能命中 → 零**生成** LLM 调用（至多一次轻量裁判，失败放行）。"""
    llm = MockLLM([GOOD_SOLUTION])
    agent = Agent(llm, tmp_store)
    r1 = agent.run_task("写一个函数统计文本词频，附带 pytest 测试")
    assert r1.ok and r1.source == "llm"
    assert llm.gen_calls == 1

    llm2 = MockLLM([])   # 生成脚本为空：若走生成路径会失败
    agent2 = Agent(llm2, tmp_store)
    r2 = agent2.run_task("统计文本词频的函数，带测试")
    assert r2.ok and r2.source == "skill"
    assert llm2.gen_calls == 0
    assert llm2.judge_calls <= 1   # 裁判至多一次


def test_judge_blocks_irrelevant_takeover(tmp_store):
    """裁判拦截：措辞相近但能力不覆盖的任务不被接管，交教师重解。"""
    llm = MockLLM([GOOD_SOLUTION])
    agent = Agent(llm, tmp_store)
    r1 = agent.run_task("写一个函数统计文本词频，附带 pytest 测试")
    assert r1.ok
    # 第二次：裁判判"不相关"→ 不接管 → 教师生成闰年解
    leap = {
        "plan": "闰年判断",
        "files": [
            {"path": "leap.py",
             "content": "def is_leap(y):\n    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)\n"},
            {"path": "tests/test_leap.py",
             "content": "from leap import is_leap\n\ndef test_leap():\n    assert is_leap(2000) and not is_leap(1900) and is_leap(2024)\n"},
        ],
        "test_cmd": "python -m pytest -q",
    }
    llm2 = MockLLM([leap])
    llm2.judge_verdict = False
    agent2 = Agent(llm2, tmp_store)
    # 措辞同族（能过双闸门），但裁判判能力不覆盖 → 拦截接管，交教师
    r2 = agent2.run_task("统计文本词频的函数，带测试")
    assert r2.ok and r2.source == "llm"
    assert llm2.judge_calls >= 1
