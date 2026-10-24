"""专家叠加测试（像人的学习）：依赖组合、注册表注入、级联重学、HSL 契约回归。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from codedojo.agent import Agent, extract_imports              # noqa: E402
from codedojo.hsl_bridge import skill_to_hsl, find_bun, find_hsl_root  # noqa: E402
from codedojo.llm import LLM                                    # noqa: E402
from codedojo.skills import SkillStore                          # noqa: E402

# 技能 A：词频模块
SKILL_A_FILES = [
    {"path": "word_count.py",
     "content": "def word_freq(text):\n    out = {}\n    for w in text.lower().split():\n        out[w] = out.get(w, 0) + 1\n    return out\n"},
    {"path": "tests/test_word_count.py",
     "content": "from word_count import word_freq\n\ndef test_basic():\n    assert word_freq('a b a') == {'a': 2, 'b': 1}\n"},
]

# 技能 B：top-k 词（import A 的模块 —— 专家叠加）
SKILL_B_FILES = [
    {"path": "topk_words.py",
     "content": "from word_count import word_freq\n\ndef top_k(text, k):\n    freq = word_freq(text)\n    return sorted(freq.items(), key=lambda kv: -kv[1])[:k]\n"},
    {"path": "tests/test_topk.py",
     "content": "from topk_words import top_k\n\ndef test_topk():\n    assert top_k('a b a c', 2) == [('a', 2), ('b', 1)]\n"},
]


class MockLLM(LLM):
    def __init__(self, script):
        super().__init__(api_key="mock")
        self.script = list(script)
        self.calls = 0
        self.gen_calls = 0
        self.judge_calls = 0
        self.judge_verdict = True
        self.seen_messages = []

    def chat_json(self, messages, temperature=0.2):
        self.calls += 1
        self.seen_messages.append(messages)
        if "能力裁判" in (messages[0]["content"] if messages else ""):
            self.judge_calls += 1
            return {"relevant": self.judge_verdict, "reason": "mock"}
        self.gen_calls += 1
        if not self.script:
            return None
        item = self.script.pop(0)
        return item if isinstance(item, dict) else json.loads(item)


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr("codedojo.skills.STORE", tmp_path / "skills.json")
    monkeypatch.setattr("codedojo.hsl_bridge.CONTRACT_DIR", tmp_path / "contracts")
    return SkillStore(tmp_path / "skills.json")


class TestDeps:
    def test_files_of_orders_deps_first(self, store):
        a = store.mount("写一个函数统计文本词频", SKILL_A_FILES, "python -m pytest -q")
        b = store.mount("取出现次数前 K 的单词", SKILL_B_FILES, "python -m pytest -q",
                        depends_on=[a.id])
        files = store.files_of(b)
        paths = [f["path"] for f in files]
        assert "word_count.py" in paths and "topk_words.py" in paths
        assert paths.index("word_count.py") < paths.index("topk_words.py")

    def test_files_of_cycle_safe(self, store):
        a = store.mount("任务A", SKILL_A_FILES, "python -m pytest -q")
        b = store.mount("任务B", SKILL_B_FILES, "python -m pytest -q", depends_on=[a.id])
        a.depends_on = [b.id]          # 人为造环
        store.save()
        files = store.files_of(b)      # 不应无限递归
        assert isinstance(files, list)

    def test_module_names_and_find_by_module(self, store):
        a = store.mount("词频统计", SKILL_A_FILES, "python -m pytest -q")
        assert "word_count" in a.module_names()
        assert store.find_by_module("word_count").id == a.id
        assert store.find_by_module("nonexistent") is None

    def test_extract_imports_ground_truth(self):
        mods = extract_imports(SKILL_B_FILES)
        assert "word_count" in mods and "topk_words" in mods


class TestStackingAgent:
    def test_registry_injected_into_prompt(self, store):
        a = store.mount("写一个函数统计文本词频", SKILL_A_FILES, "python -m pytest -q")
        llm = MockLLM([{"plan": "x", "files": SKILL_A_FILES, "test_cmd": "python -m pytest -q",
                        "imports": [a.id]}])
        agent = Agent(llm, store)
        r = agent.run_task("写一个完全不同的判断闰年函数，带测试")
        assert llm.seen_messages, "mock 应捕获消息"
        first_user = llm.seen_messages[0][1]["content"]
        assert "已挂载专家" in first_user and a.id in first_user
        assert "word_count.py" in first_user or "word_freq" in first_user

    def test_mount_records_ground_truth_deps(self, store):
        store.mount("写一个函数统计文本词频", SKILL_A_FILES, "python -m pytest -q")
        llm = MockLLM([{"plan": "复用词频", "files": SKILL_B_FILES,
                        "test_cmd": "python -m pytest -q", "imports": []}])
        agent = Agent(llm, store)
        r = agent.run_task("取出现次数前 K 的单词，带测试")
        assert r.ok
        mounted = store.skills[r.skill_id]
        # 未声明 imports，但代码 import word_count -> 地面真值命中
        assert any("word_count" in store.skills[d].module_names()
                   for d in mounted.depends_on)

    def test_composed_takeover_zero_llm(self, store):
        """A、B 都挂载后：B 的同族任务接管时应带上 A 的文件，零 LLM。"""
        a = store.mount("写一个函数统计文本词频", SKILL_A_FILES, "python -m pytest -q")
        store.mount("取出现次数前 K 的单词", SKILL_B_FILES, "python -m pytest -q",
                    depends_on=[a.id])
        llm = MockLLM([])             # 生成脚本空：若走生成会失败
        agent = Agent(llm, store)
        r = agent.run_task("取出现次数前 K 的单词的函数")
        assert r.ok and r.source == "skill" and llm.gen_calls == 0
        assert llm.judge_calls <= 1
        assert r.depends_on == [a.id]

    def test_cascade_relearn_after_base_retires(self, store):
        """底层 A 退役后：B 接管验证失败 -> 教师重学（级联，像人的学习）。"""
        a = store.mount("写一个函数统计文本词频", SKILL_A_FILES, "python -m pytest -q")
        store.mount("取出现次数前 K 的单词", SKILL_B_FILES, "python -m pytest -q",
                    depends_on=[a.id])
        for _ in range(3):            # A 退役
            a.record(False)
        store.save()
        assert a.retired

        # B 接管：files_of 仍含 A 文件（档案保留）-> 测试应过？——A 文件仍在，测试通过；
        # 级联重学的触发点应是 B 自身测试失败。构造 B 依赖失效场景：
        # 把 A 的实现文件替换为坏版本（模拟"底层专家被证伪"）
        a.files[0]["content"] = "def word_freq(text):\n    return None\n"
        store.save()

        llm = MockLLM([{"plan": "重学 topk",
                        "files": [
                            {"path": "topk_words.py",
                             "content": "def top_k(text, k):\n    freq = {}\n    for w in text.lower().split():\n        freq[w] = freq.get(w, 0) + 1\n    return sorted(freq.items(), key=lambda kv: -kv[1])[:k]\n"},
                            {"path": "tests/test_topk.py",
                             "content": "from topk_words import top_k\n\ndef test_topk():\n    assert top_k('a b a c', 2) == [('a', 2), ('b', 1)]\n"},
                        ],
                        "test_cmd": "python -m pytest -q", "imports": []}])
        agent = Agent(llm, store)
        r = agent.run_task("取出现次数前 K 的单词")
        # B 接管验证失败（A 坏了）-> 走教师重学 -> 成功
        assert r.ok and r.source == "llm" and llm.gen_calls == 1


class TestHslContractRegression:
    def test_single_braces_in_arms(self, store):
        s = store.mount("词频统计", SKILL_A_FILES, "python -m pytest -q")
        text = skill_to_hsl(s)
        assert "Signal::Proceed { note } => {" in text
        assert "{{ note }}" not in text and "{{ summary }}" not in text

    def test_dependency_annotation(self, store):
        a = store.mount("词频", SKILL_A_FILES, "python -m pytest -q")
        b = store.mount("topk", SKILL_B_FILES, "python -m pytest -q", depends_on=[a.id])
        text = skill_to_hsl(b)
        assert "依赖（专家叠加）: {}".format(a.id) in text

    def test_real_dhv_check(self, store):
        if find_bun() is None or find_hsl_root() is None:
            pytest.skip("bun/HSL 工具链不可用")
        from codedojo import hsl_bridge
        s = store.mount("词频统计回归", SKILL_A_FILES, "python -m pytest -q")
        r = hsl_bridge.write_contract(s)
        assert r["check"] == "pass", r


class TestGates:
    """误接管与冗余依赖的修复验证。"""

    def test_dual_gate_rejects_superset_task(self, store):
        """反例回归：'批量+求和'是'单转换'的需求超集——重叠系数会误放行，
        Jaccard 下限必须拦下（真实误接管场景）。"""
        store.mount("写一个函数把罗马数字字符串转换成整数，附带 pytest 测试",
                    SKILL_A_FILES, "python -m pytest -q")
        superset = "写一个函数批量把一组罗马数字全部转换成整数并求和（复用已挂载专家的模块），附带 pytest 测试"
        assert store.match(superset) is None
        same_family = "把罗马数字字符串转为整数的函数，带测试"
        assert store.match(same_family) is not None

    def test_declared_deps_without_import_are_dropped(self, store):
        """声明依赖但代码没 import：不入库（防教师冗余复用）。"""
        a = store.mount("词频统计", SKILL_A_FILES, "python -m pytest -q")
        leap = [
            {"path": "leap.py",
             "content": "def is_leap(y):\n    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)\n"},
            {"path": "tests/test_leap.py",
             "content": "from leap import is_leap\n\ndef test_leap():\n    assert is_leap(2000)\n"},
        ]
        llm = MockLLM([{"plan": "闰年", "files": leap, "test_cmd": "python -m pytest -q",
                         "imports": [a.id]}])   # 声明依赖 A 但没 import 它
        agent = Agent(llm, store)
        r = agent.run_task("判断闰年的函数，带测试")
        assert r.ok
        assert store.skills[r.skill_id].depends_on == []

    def test_registry_filtered_by_capability(self, store):
        """注册表按能力相关性过滤：词频专家不进闰年任务的注册表。"""
        a = store.mount("词频统计", SKILL_A_FILES, "python -m pytest -q",
                        capabilities=["统计文本中每个单词的出现次数"])
        agent = Agent(MockLLM([]), store)
        assert a.id not in agent._registry_text("判断闰年的函数，带测试")
        assert a.id in agent._registry_text("统计单词出现次数的函数，带测试")

    def test_capabilities_persisted(self, store):
        store.mount("词频统计", SKILL_A_FILES, "python -m pytest -q",
                    capabilities=["统计文本词频"])
        store2 = SkillStore(store.path)
        s = list(store2.skills.values())[0]
        assert s.capabilities == ["统计文本词频"]
        assert s.capability_overlap("统计词频的函数")
        assert not s.capability_overlap("配置 nginx 反向代理")
