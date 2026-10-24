"""CodeDojo 主循环：技能接管 -> LLM 生成 -> 沙箱验证 -> 修复回路 -> 挂载。

专家叠加（像人的学习）：教师生成时能看见已挂载的专家（注册表），
新解法可 import 已验证模块（组合即学习）；依赖关系入库；
底层专家退役 -> 上层技能接管验证自然失败 -> 级联重学。
"""

import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Set

from codedojo import hsl_bridge
from codedojo.llm import LLM
from codedojo.sandbox import Sandbox
from codedojo.skills import SkillStore

MAX_FIX_ITERATIONS = 3
REGISTRY_BUDGET = 8000   # 专家注册表字符预算

SYSTEM_PROMPT = """你是 CodeDojo 的编码引擎，在 Windows 沙箱里完成任务并自验。

工作方式：
1. 阅读任务，规划最小的可测实现；
2. 产出 Python 源文件与对应 pytest 测试文件；
3. 测试命令统一用：python -m pytest -q（环境已装 pytest）。

严格输出一个 JSON 对象（不要 markdown 代码围栏）：
{
  "plan": "一两句实现思路",
  "files": [{"path": "相对路径.py", "content": "完整文件内容"}],
  "test_cmd": "python -m pytest -q",
  "imports": ["你复用的专家技能 id"]
}

专家叠加：如果下面提供了"已挂载专家"清单，你可以直接 import 它们的模块
（沙箱里会自动提供这些文件）——优先复用而不是重写；在 imports 数组里
声明你复用了哪些专家 id。

硬性要求：
- files 至少 2 个：实现 + tests/test_*.py；
- 只用 Python 标准库（除非任务明确要求且你确认环境有）；
- 测试要真实断言行为（不是只 import）；
- 文件内容是完整可运行的，不含 TODO。"""


@dataclass
class TaskResult:
    task: str
    ok: bool
    source: str                 # "skill" | "llm"
    skill_id: str = ""
    iterations: int = 0
    files: List[dict] = field(default_factory=list)
    test_output: str = ""
    plan: str = ""
    error: str = ""
    elapsed_ms: float = 0.0
    llm_calls: int = 0
    tokens: dict = field(default_factory=dict)
    hsl_contract: dict = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)


_IMPORT_RE = re.compile(r"^\s*(?:from\s+([A-Za-z_][A-Za-z0-9_]*)|import\s+([A-Za-z_][A-Za-z0-9_]*))",
                        re.MULTILINE)


def extract_imports(files: List[dict]) -> Set[str]:
    """从代码文件里提取 import 的顶层模块名（地面真值）。"""
    mods: Set[str] = set()
    for f in files:
        if not f["path"].endswith(".py") or f["path"].startswith("tests/"):
            # tests 也算：测试 import 被测模块很正常，同样计入
            pass
        for m in _IMPORT_RE.finditer(f.get("content", "")):
            mods.add(m.group(1) or m.group(2))
    return mods


class Agent:
    def __init__(self, llm: Optional[LLM] = None, store: Optional[SkillStore] = None,
                 log: Optional[Callable[[str], None]] = None) -> None:
        self.llm = llm or LLM()
        self.store = store or SkillStore()
        self._log = log or (lambda msg: None)

    # ------------------------------------------------------------ 专家注册表
    def _registry_text(self) -> str:
        """已挂载专家清单（给教师看）：id / 任务 / 模块名 / 源码（预算内）。"""
        actives = [s for s in self.store.skills.values() if not s.retired]
        if not actives:
            return ""
        parts, budget = [], REGISTRY_BUDGET
        for s in actives:
            entry = "专家 {}: {}（任务：{}）".format(s.id, ", ".join(sorted(s.module_names())) or "-",
                                              s.task[:60])
            for f in s.files:
                if f["path"].startswith("tests/") or not f["path"].endswith(".py"):
                    continue
                src = f["content"]
                if len(src) + len(entry) < budget:
                    entry += "\n--- {} ---\n{}".format(f["path"], src)
                    budget -= len(src)
            parts.append(entry)
            if budget < 500:
                break
        return "\n\n".join(parts)

    def _resolve_dep_ids(self, files: List[dict], declared: Optional[list],
                         exclude_id: Optional[str] = None) -> List[str]:
        """依赖技能 id = 声明 imports ∪ 代码实际 import 命中的专家模块。

        exclude_id：正被重学的技能自身——新解法 import 自己的模块名是常态
        （重写 topk_words），不能据此把"旧自己"（及其坏依赖）拖进沙箱。
        """
        dep_ids: List[str] = []
        for d in (declared or []):
            sid = str(d)
            if sid != exclude_id and sid in self.store.skills and sid not in dep_ids:
                dep_ids.append(sid)
        for module in extract_imports(files):
            provider = self.store.find_by_module(module)
            if (provider is not None and provider.id != exclude_id
                    and provider.id not in dep_ids):
                dep_ids.append(provider.id)
        return dep_ids

    def _dep_files(self, dep_ids: List[str]) -> List[dict]:
        """依赖技能的完整文件集（含传递依赖），供沙箱写入。"""
        out: List[dict] = []
        seen: set = set()
        for sid in dep_ids:
            s = self.store.skills.get(sid)
            if s is None:
                continue
            for f in self.store.files_of(s):
                if f["path"] not in seen:
                    seen.add(f["path"])
                    out.append(f)
        return out

    # ------------------------------------------------------------------ 主入口
    def run_task(self, task: str) -> TaskResult:
        start = time.perf_counter()
        task_id = "t_" + uuid.uuid4().hex[:10]

        # 1) 技能接管（GraphDojo 的"图"）：匹配 -> 带依赖重验 -> 直接用
        skill = self.store.match(task)
        if skill is not None:
            self._log("[dojo] 技能命中 {}（uses={}，依赖 {}）→ 重验".format(
                skill.id, skill.uses, len(skill.depends_on)))
            sb = Sandbox(task_id + "_skill")
            try:
                sb.write_files(self.store.files_of(skill))   # 依赖 + 自身
                r = sb.run(skill.test_cmd)
                if r["ok"]:
                    skill.record(True)
                    self.store.save()
                    self._log("[dojo] 技能验证通过，零 LLM 接管")
                    return TaskResult(
                        task=task, ok=True, source="skill", skill_id=skill.id,
                        files=skill.files, test_output=r["stdout"],
                        elapsed_ms=(time.perf_counter() - start) * 1000,
                        depends_on=skill.depends_on)
                # 验证失败：技能失效（环境变迁或底层依赖退役），走教师重学
                skill.record(False)
                self.store.save()
                self._log("[dojo] 技能验证失败，转教师重学")
            finally:
                sb.cleanup()

        # 2) 教师生成 + 修复回路
        if not self.llm.ready:
            return TaskResult(task=task, ok=False, source="llm",
                              error="无匹配技能且缺少 DEEPSEEK_API_KEY",
                              elapsed_ms=(time.perf_counter() - start) * 1000)

        registry = self._registry_text()
        first_user = "任务：{}".format(task)
        if registry:
            first_user += "\n\n=== 已挂载专家（可 import 复用，在 imports 里声明）===\n" + registry
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": first_user}]
        sb = Sandbox(task_id)
        result = TaskResult(task=task, ok=False, source="llm",
                            elapsed_ms=0.0)
        try:
            for it in range(1, MAX_FIX_ITERATIONS + 1):
                self._log("[dojo] 教师生成（第 {} 次）".format(it))
                data = self.llm.chat_json(messages)
                if not data or "files" not in data or not data["files"]:
                    messages.append({"role": "user",
                                     "content": "输出缺少 files，请按协议重新输出 JSON。"})
                    continue
                files = data["files"]
                test_cmd = data.get("test_cmd") or "python -m pytest -q"
                dep_ids = self._resolve_dep_ids(
                    files, data.get("imports"),
                    exclude_id=(skill.id if skill is not None else None))
                try:
                    sb.write_files(self._dep_files(dep_ids))   # 依赖先落沙箱
                    sb.write_files(files)                       # 自身后写（可覆盖）
                except ValueError as exc:
                    messages.append({"role": "user",
                                     "content": "文件路径非法：{}，请重新输出。".format(exc)})
                    continue
                r = sb.run(test_cmd)
                result.iterations = it
                result.files = files
                result.plan = data.get("plan", "")
                result.test_output = (r["stdout"] + "\n" + r["stderr"]).strip()
                if r["ok"]:
                    result.ok = True
                    # 3) 挂载：验证通过的解法成为技能（记录依赖）+ HSL 契约
                    skill = self.store.mount(task, files, test_cmd, depends_on=dep_ids)
                    skill.depends_on = [d for d in skill.depends_on if d != skill.id]
                    self.store.save()
                    result.skill_id = skill.id
                    result.depends_on = skill.depends_on
                    contract = hsl_bridge.write_contract(skill)
                    result.hsl_contract = contract
                    self._log("[dojo] 验证通过，挂载技能 {}（依赖 {}，HSL 契约: {}）".format(
                        skill.id, len(skill.depends_on), contract["check"]))
                    self._log("[dojo] 契约文件: {}".format(contract["path"]))
                    break
                self._log("[dojo] 测试未过（第 {} 次），回喂修复".format(it))
                messages.append({"role": "assistant", "content": "(上一次输出已执行)"})
                messages.append({
                    "role": "user",
                    "content": "测试失败。输出：\n{}\n请修复代码后重新输出完整 JSON（全部文件）。".format(
                        (r["stdout"] + r["stderr"])[:4000])})
        finally:
            sb.cleanup()

        result.elapsed_ms = (time.perf_counter() - start) * 1000
        result.llm_calls = self.llm.calls
        result.tokens = self.llm.cost()
        return result
