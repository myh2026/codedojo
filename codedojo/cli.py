"""CodeDojo CLI：无头模式（与桌面模式同引擎）。

用法：
    python -m codedojo.cli "写一个函数统计文本词频，附带 pytest 测试"
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from codedojo.agent import Agent          # noqa: E402
from codedojo.llm import LLM              # noqa: E402
from codedojo.skills import SkillStore    # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    task = " ".join(sys.argv[1:])
    agent = Agent(LLM(), SkillStore(), log=lambda m: print(m, flush=True))
    result = agent.run_task(task)
    print()
    print("== 结果 ==")
    print("  成功: {} | 来源: {} | 迭代: {} | 用时 {:.0f}ms".format(
        result.ok, result.source, result.iterations, result.elapsed_ms))
    if result.llm_calls:
        print("  LLM: {} 次调用, tokens {}".format(
            result.llm_calls, result.tokens.get("tokens_in", 0)))
    if result.files:
        print("  文件: {}".format(", ".join(f["path"] for f in result.files)))
    if result.error:
        print("  错误: {}".format(result.error))
    print("  技能库: {}".format(agent.store.stats()))
    # 产物落盘供查看
    out = Path.home() / ".codedojo" / "last_result.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "task": result.task, "ok": result.ok, "source": result.source,
        "files": [{"path": f["path"]} for f in result.files],
        "test_output": result.test_output[-2000:]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print("  详情: {}".format(out))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
