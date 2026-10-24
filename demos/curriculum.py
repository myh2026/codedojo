# -*- coding: utf-8 -*-
"""CodeDojo 学习曲线实验：量化"像人的学习"。

课程表：10 个独立任务族（首轮教学、二轮换措辞测接管）+ 3 个组合任务
（预期复用已有专家模块，叠加依赖）。

测量：
  1. 每任务的生成调用 / 裁判调用 / tokens / 用时 / 来源
  2. 累计曲线：技能数、依赖边数、生成调用累计（应趋于平缓）
  3. 接管率（二轮同族应零生成接管）

运行：DEEPSEEK_API_KEY=... python demos/curriculum.py [--fresh]
输出：curriculum_results.md / .json
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from codedojo.agent import Agent          # noqa: E402
from codedojo.llm import LLM              # noqa: E402
from codedojo.skills import SkillStore    # noqa: E40jo2  # noqa: E402

ROOT = Path(__file__).parents[1]

CURRICULUM = [
    # (族名, 首轮任务, 二轮换措辞)
    ("word_freq", "写一个函数统计一段英文文本里每个单词的出现次数（不区分大小写），附带 pytest 测试",
     "统计单词出现次数的函数，带测试"),
    ("leap", "写一个函数判断输入年份是否为闰年，附带 pytest 测试",
     "判断闰年的函数，带测试"),
    ("palindrome", "写一个函数判断字符串是否为回文（忽略大小写和空格），附带 pytest 测试",
     "回文判断函数，带测试"),
    ("roman", "写一个函数把罗马数字字符串转换成整数，附带 pytest 测试",
     "罗马数字转整数的函数，带测试"),
    ("temp", "写一个函数把摄氏温度转换为华氏温度，附带 pytest 测试",
     "摄氏度转华氏度的函数，带测试"),
    ("prime", "写一个函数判断一个整数是否为素数，附带 pytest 测试",
     "素数判断函数，带测试"),
    ("reverse", "写一个函数反转字符串中的单词顺序，附带 pytest 测试",
     "把字符串里单词倒序排列的函数，带测试"),
    ("fizzbuzz", "写一个函数对 1 到 n 做 FizzBuzz（3 的倍数 Fizz、5 的倍数 Buzz、都是 Buzz/Fizz/FizzBuzz），附带 pytest 测试",
     "FizzBuzz 函数，带测试"),
    ("dedupe", "写一个函数去除列表中的重复元素并保持原顺序，附带 pytest 测试",
     "列表去重保序函数，带测试"),
    ("factorial", "写一个函数计算阶乘（大数用迭代），附带 pytest 测试",
     "阶乘计算函数，带测试"),
]

COMPOSITES = [
    ("top_word", "写一个函数找一段英文文本中出现次数最多的单词（可复用已挂载专家模块），附带 pytest 测试"),
    ("leap_feb", "写一个函数返回某年份 2 月的天数（可复用已挂载专家模块），附带 pytest 测试"),
    ("roman_batch_sum", "写一个函数把一组罗马数字全部转换成整数并求和（可复用已挂载专家模块），附带 pytest 测试"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fresh", action="store_true", help="清空技能库从零开始")
    args = ap.parse_args()

    store_path = Path.home() / ".codedojo" / "skills.json"
    if args.fresh and store_path.exists():
        store_path.rename(store_path.with_suffix(".pre-curriculum.json"))
        print("[curriculum] 技能库已备份并清零")

    llm = LLM()
    if not llm.ready:
        print("缺少 DEEPSEEK_API_KEY")
        return 2
    agent = Agent(llm, SkillStore(),
                  log=lambda m: print(m, flush=True))

    rows = []

    def record(phase, family, task, r, llm_before):
        cost = llm.cost()
        row = {
            "phase": phase, "family": family, "task": task[:50],
            "ok": r.ok, "source": r.source, "iterations": r.iterations,
            "gen_calls": cost["llm_calls"] - llm_before["llm_calls"],
            "tokens_in": cost["tokens_in"] - llm_before["tokens_in"],
            "tokens_out": cost["tokens_out"] - llm_before["tokens_out"],
            "elapsed_ms": round(r.elapsed_ms),
            "deps": len(r.depends_on),
            "skills_total": agent.store.stats()["active"],
            "dep_links": agent.store.stats()["dep_links"],
        }
        rows.append(row)
        print("  -> {} {} gen={} tok={}/{} {:.0f}ms 技能={} 依赖边={}".format(
            r.source, "OK" if r.ok else "FAIL", row["gen_calls"],
            row["tokens_in"], row["tokens_out"], row["elapsed_ms"],
            row["skills_total"], row["dep_links"]), flush=True)

    print("== 第一轮：10 族教学（每族 1 次生成）==")
    for family, teach, _ in CURRICULUM:
        llm_before = llm.cost()
        r = agent.run_task(teach)
        record("teach", family, teach, r, llm_before)

    print("\n== 第二轮：同族换措辞（应零生成接管）==")
    for family, _, quiz in CURRICULUM:
        llm_before = llm.cost()
        r = agent.run_task(quiz)
        record("rephrase", family, quiz, r, llm_before)

    print("\n== 第三轮：组合任务（预期叠加依赖）==")
    for family, task in COMPOSITES:
        llm_before = llm.cost()
        r = agent.run_task(task)
        record("composite", family, task, r, llm_before)

    # ---- 汇总 ----
    def agg(phase, key):
        vals = [r[key] for r in rows if r["phase"] == phase]
        return sum(vals) if vals else 0

    n_teach = len(CURRICULUM)
    n_rephrase = len(CURRICULUM)
    rephrase_takeovers = sum(1 for r in rows
                             if r["phase"] == "rephrase" and r["source"] == "skill")
    composite_stacked = sum(1 for r in rows
                            if r["phase"] == "composite" and r["deps"] >= 1)

    summary = {
        "teach_gen_calls": agg("teach", "gen_calls"),
        "rephrase_gen_calls": agg("rephrase", "gen_calls"),
        "rephrase_takeover_rate": rephrase_takeovers / n_rephrase,
        "composite_stacked": composite_stacked,
        "final_skills": rows[-1]["skills_total"] if rows else 0,
        "final_dep_links": rows[-1]["dep_links"] if rows else 0,
        "total_tokens_in": sum(r["tokens_in"] for r in rows),
        "total_tokens_out": sum(r["tokens_out"] for r in rows),
    }

    md = ["# CodeDojo 学习曲线实验（真实 DeepSeek）", "",
          "| 阶段 | 任务 | 族 | 来源 | 生成调用 | tokens 入/出 | 用时 ms | 新依赖 | 技能累计 | 依赖边累计 |",
          "|:---|:---|:---|:---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        md.append("| {} | {} | {} | {} | {} | {}/{} | {} | {} | {} | {} |".format(
            r["phase"], r["task"], r["family"], r["source"], r["gen_calls"],
            r["tokens_in"], r["tokens_out"], r["elapsed_ms"], r["deps"],
            r["skills_total"], r["dep_links"]))
    md += [
        "", "## 汇总", "",
        "- 教学轮生成调用：**{}**（10 族）".format(summary["teach_gen_calls"]),
        "- 换措辞轮生成调用：**{}**（接管率 {:.0%}）".format(
            summary["rephrase_gen_calls"], summary["rephrase_takeover_rate"]),
        "- 组合任务叠加依赖：**{}/3**".format(summary["composite_stacked"]),
        "- 期末技能 **{}** 个、依赖边 **{}** 条".format(
            summary["final_skills"], summary["final_dep_links"]),
        "- 总 tokens：入 {} / 出 {}".format(
            summary["total_tokens_in"], summary["total_tokens_out"]),
    ]
    (ROOT / "curriculum_results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (ROOT / "curriculum_results.json").write_text(
        json.dumps({"rows": rows, "summary": summary}, indent=2, ensure_ascii=False),
        encoding="utf-8")
    print("\n== 汇总 ==")
    for k, v in summary.items():
        print("  {}: {}".format(k, v))
    print("saved curriculum_results.md / .json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
