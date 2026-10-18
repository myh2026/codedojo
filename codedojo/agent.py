"""CodeDojo 主循环：技能接管 -> LLM 生成 -> 沙箱验证 -> 修复回路 -> 挂载。"""

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from codedojo.llm import LLM
from codedojo.sandbox import Sandbox
from codedojo.skills import SkillStore

MAX_FIX_ITERATIONS = 3

SYSTEM_PROMPT = """你是 CodeDojo 的编码引擎，在 Windows 沙箱里完成任务并自验。

工作方式：
1. 阅读任务，规划最小的可测实现；
2. 产出 Python 源文件与对应 pytest 测试文件；
3. 测试命令统一用：python -m pytest -q（环境已装 pytest）。

严格输出一个 JSON 对象（不要 markdown 代码围栏）：
{
  "plan": "一两句实现思路",
  "files": [{"path": "相对路径.py", "content": "完整文件内容"}],
  "test_cmd": "python -m pytest -q"
}

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


class Agent:
    def __init__(self, llm: Optional[LLM] = None, store: Optional[SkillStore] = None,
                 log: Optional[Callable[[str], None]] = None) -> None:
        self.llm = llm or LLM()
        self.store = store or SkillStore()
        self._log = log or (lambda msg: None)

    # ------------------------------------------------------------------ 主入口
    def run_task(self, task: str) -> TaskResult:
        start = time.perf_counter()
        task_id = "t_" + uuid.uuid4().hex[:10]

        # 1) 技能接管（GraphDojo 的"图"）：匹配 -> 沙箱重验 -> 直接用
        skill = self.store.match(task)
        if skill is not None:
            self._log("[dojo] 技能命中 {}（uses={}）→ 重验".format(skill.id, skill.uses))
            sb = Sandbox(task_id + "_skill")
            try:
                sb.write_files(skill.files)
                r = sb.run(skill.test_cmd)
                if r["ok"]:
                    skill.record(True)
                    self.store.save()
                    self._log("[dojo] 技能验证通过，零 LLM 接管")
                    return TaskResult(
                        task=task, ok=True, source="skill", skill_id=skill.id,
                        files=skill.files, test_output=r["stdout"],
                        elapsed_ms=(time.perf_counter() - start) * 1000)
                # 验证失败：技能失效（环境变迁），走教师重学
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

        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": "任务：{}".format(task)}]
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
                try:
                    sb.write_files(files)
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
                    # 3) 挂载：验证通过的解法成为技能
                    skill = self.store.mount(task, files, test_cmd)
                    result.skill_id = skill.id
                    self._log("[dojo] 验证通过，挂载技能 {}".format(skill.id))
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
