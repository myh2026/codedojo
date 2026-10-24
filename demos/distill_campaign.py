# -*- coding: utf-8 -*-
"""CodeDojo 蒸馏战役（deepseek-v4.1-flash-1017 教师）：七阶段全流程。

规程见 docs/DISTILL_PLAN.md。预算硬闸默认 $2.00。
运行：DEEPSEEK_API_KEY=... uv run python demos/distill_campaign.py [--budget 2.0] [--fresh]
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from codedojo.agent import Agent            # noqa: E402
from codedojo.llm import LLM                # noqa: E402
from codedojo.skills import SkillStore      # noqa: E402

ROOT = Path(__file__).parents[1]

TEACH = [
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
    ("fizzbuzz", "写一个函数对 1 到 n 做 FizzBuzz（3 的倍数 Fizz、5 的倍数 Buzz、都是 FizzBuzz），附带 pytest 测试",
     "FizzBuzz 函数，带测试"),
    ("dedupe", "写一个函数去除列表中的重复元素并保持原顺序，附带 pytest 测试",
     "列表去重保序函数，带测试"),
    ("factorial", "写一个函数计算阶乘（大数用迭代），附带 pytest 测试",
     "阶乘计算函数，带测试"),
    ("base64", "写一个函数对字符串做 base64 编码和解码两个函数，附带 pytest 测试",
     "base64 编码解码函数，带测试"),
    ("gcd", "写两个函数分别求最大公约数和最小公倍数，附带 pytest 测试",
     "最大公约数最小公倍数函数，带测试"),
]

COMPOSITES = [
    ("top_word", "写一个函数找一段英文文本中出现次数最多的单词（可复用已挂载专家模块），附带 pytest 测试"),
    ("feb_days", "写一个函数返回某年份 2 月的天数（可复用已挂载专家模块），附带 pytest 测试"),
    ("roman_batch", "写一个函数把一组罗马数字全部转换成整数并求和（可复用已挂载专家模块），附带 pytest 测试"),
    ("freq_table", "写一个函数把文本词频输出成『单词:次数』逗号分隔的字符串（可复用已挂载专家模块），附带 pytest 测试"),
]

HOLDOUT = [
    ("caesar", "写一个函数对字符串做凯撒密码加密（位移 3），附带 pytest 测试"),
    ("isbn", "写一个函数校验 ISBN-10 号码是否合法，附带 pytest 测试"),
    ("nicomachus", "写一个函数验证尼科彻斯定理：任一整数的立方等于连续奇数之和，返回这些奇数，附带 pytest 测试"),
    ("brackets", "写一个函数判断括号字符串是否匹配（含 ()[]{} 三种），附带 pytest 测试"),
]

DUEL_FAMILIES = ["word_freq", "roman", "prime"]


class BudgetBlown(Exception):
    pass


class BudgetedLLM(LLM):
    """带预算硬闸的 LLM：每次调用前检查累计成本。"""

    def __init__(self, *a, budget_usd: float = 2.0, **kw):
        super().__init__(*a, **kw)
        self.budget_usd = budget_usd

    def chat(self, *a, **kw):
        if self.cost_usd >= self.budget_usd:
            raise BudgetBlown("预算耗尽：${:.4f}/${:.2f}".format(self.cost_usd, self.budget_usd))
        return super().chat(*a, **kw)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=2.0)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    if args.fresh:
        p = Path.home() / ".codedojo" / "skills.json"
        if p.exists():
            p.rename(p.with_suffix(".pre-campaign.json"))
            print("[campaign] 技能库已备份清零")

    llm = BudgetedLLM(budget_usd=args.budget)
    if not llm.ready:
        print("缺少 DEEPSEEK_API_KEY")
        return 2
    print("[campaign] 教师模型：{}（预算闸 ${:.2f}）".format(llm.model, args.budget))

    agent = Agent(llm, SkillStore(), log=lambda m: print("  " + m, flush=True))
    rows = []

    def run_one(phase, family, task):
        before = llm.cost()
        t0 = time.perf_counter()
        r = agent.run_task(task)
        wall_s = time.perf_counter() - t0
        after = llm.cost()
        row = {
            "phase": phase, "family": family, "task": task[:46],
            "ok": r.ok, "source": r.source, "iterations": r.iterations,
            "gen_calls_delta": after["llm_calls"] - before["llm_calls"],
            "tokens_delta": after["tokens_in"] - before["tokens_in"],
            "tokens_out_delta": after["tokens_out"] - before["tokens_out"],
            "cost_usd_delta": round(after["cost_usd"] - before["cost_usd"], 6),
            "skill_s": round(wall_s, 2),
            "deps": len(r.depends_on),
            "skills_total": agent.store.stats()["active"],
            "dep_links": agent.store.stats()["dep_links"],
            "contract": r.hsl_contract.get("check", ""),
        }
        rows.append(row)
        print("  -> {} {} | gen={} ${:.5f} {:.1f}s | 技能={} 依赖边={}".format(
            r.source, "OK" if r.ok else "FAIL", row["gen_calls_delta"],
            row["cost_usd_delta"], wall_s,
            row["skills_total"], row["dep_links"]), flush=True)
        return r

    try:
        # P0 自检
        print("\n== P0 模型自检 ==")
        pong = llm.chat_json([{"role": "user", "content": '输出 {"pong": true}'}],
                             thinking=False, max_tokens=64)
        print("  P0: {} | 模型 {} | 成本 ${:.6f}".format(
            "OK" if pong else "FAIL", llm.model, llm.cost_usd))

        # P1 教学
        print("\n== P1 教学（12 族）==")
        for fam, teach, _ in TEACH:
            run_one("teach", fam, teach)

        # P2 换措辞
        print("\n== P2 换措辞接管（12 族）==")
        for fam, _, quiz in TEACH:
            run_one("rephrase", fam, quiz)

        # P3 叠加
        print("\n== P3 组合叠加（4 任务）==")
        for fam, task in COMPOSITES:
            run_one("composite", fam, task)

        # P4 保留集
        print("\n== P4 保留集（4 个全新族，应零误接管）==")
        for fam, task in HOLDOUT:
            run_one("holdout", fam, task)

        # P5 蒸馏对照
        print("\n== P5 蒸馏对照（教师直解 vs 技能接管）==")
        duels = []
        for fam, teach, _ in TEACH:
            if fam not in DUEL_FAMILIES:
                continue
            quiz = dict(TEACH)[fam]  # 换措辞文本
            # 路径 A：技能接管（正常 agent）
            ra = run_one("duel_skill", fam + "/skill", quiz)
            # 路径 B：教师直解（干净沙箱：临时禁用匹配）
            saved = agent.store.skills
            agent.store.skills = {}
            rb = run_one("duel_teacher", fam + "/teacher", quiz)
            agent.store.skills = saved
            duels.append({
                "family": fam,
                "skill": {"ok": ra.ok, "s": rows[-2]["skill_s"], "usd": rows[-2]["cost_usd_delta"]},
                "teacher": {"ok": rb.ok, "s": rows[-1]["skill_s"], "usd": rows[-1]["cost_usd_delta"]},
            })

    except BudgetBlown as exc:
        print("\n[campaign] {}".format(exc))
    finally:
        # P6 报告
        c = llm.cost()
        rep = [r for r in rows if r["phase"] == "rephrase"]
        hold = [r for r in rows if r["phase"] == "holdout"]
        comp = [r for r in rows if r["phase"] == "composite"]
        takeover = sum(1 for r in rep if r["source"] == "skill") / max(1, len(rep))
        hold_takeover = sum(1 for r in hold if r["source"] == "skill") / max(1, len(hold))
        stacked = sum(1 for r in comp if r["deps"] >= 1)
        speedup = None
        if duels:
            ts = sum(d["teacher"]["s"] for d in duels) / len(duels)
            ss = sum(d["skill"]["s"] for d in duels) / len(duels)
            tu = sum(d["teacher"]["usd"] for d in duels) / len(duels)
            su = sum(d["skill"]["usd"] for d in duels) / len(duels)
            speedup = {"teacher_s": round(ts, 2), "skill_s": round(ss, 2),
                       "latency_x": round(ts / max(ss, 1e-9), 1),
                       "teacher_usd": round(tu, 6), "skill_usd": round(su, 6),
                       "cost_x": round(tu / max(su, 1e-9), 1)}
        summary = {
            "model": llm.model,
            "takeover_rate_rephrase": takeover,
            "takeover_rate_holdout": hold_takeover,
            "composite_stacked": stacked,
            "total_tasks": len(rows),
            "ok_tasks": sum(1 for r in rows if r["ok"]),
            "total_cost_usd": c["cost_usd"],
            "cache_hit_ratio": (c["tokens_in_hit"] / c["tokens_in"]) if c["tokens_in"] else 0.0,
            "tokens": c,
            "speedup": speedup,
            "duels": duels,
        }
        md = ["# 蒸馏战役结果（{}）".format(llm.model), "",
              "| 阶段 | 族 | 任务 | 来源 | 成功 | 生成调用 | 成本$ | 秒 | 依赖 | 契约 |",
              "|:--|:--|:--|:--|:--|--:|--:|--:|--:|:--|"]
        for r in rows:
            md.append("| {} | {} | {} | {} | {} | {} | {:.5f} | {} | {} | {} |".format(
                r["phase"], r["family"], r["task"], r["source"], r["ok"],
                r["gen_calls_delta"], r["cost_usd_delta"], r["skill_s"],
                r["deps"], r["contract"] or "-"))
        md += ["", "## 汇总", "",
               "- 换措辞零生成接管率：**{:.0%}**".format(takeover),
               "- 保留集误接管率：**{:.0%}**（应为 0）".format(hold_takeover),
               "- 组合叠加（依赖≥1）：**{}/{}**".format(stacked, len(comp)),
               "- 任务成功：{}/{}".format(summary["ok_tasks"], summary["total_tasks"]),
               "- 总成本：**${:.4f}**（缓存命中率 {:.0%}）".format(
                   c["cost_usd"], summary["cache_hit_ratio"])]
        if speedup:
            md += ["- 蒸馏对照：教师 {:.1f}s/${:.5f} vs 技能 {:.1f}s/${:.5f}"
                   " → **延迟 {:.1f}× / 成本 {:.1f}×**".format(
                       speedup["teacher_s"], speedup["teacher_usd"],
                       speedup["skill_s"], speedup["skill_usd"],
                       speedup["latency_x"], speedup["cost_x"])]
        (ROOT / "distill_campaign_results.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        (ROOT / "distill_campaign_results.json").write_text(
            json.dumps({"rows": rows, "summary": summary}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print("\n== P6 汇总 ==")
        for k, v in summary.items():
            if k not in ("duels",):
                print("  {}: {}".format(k, v))
        print("saved distill_campaign_results.md / .json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
