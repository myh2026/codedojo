"""技能库：验证通过的解法挂载为持久技能（GraphDojo 的"图"）。

- 挂载：解法必须先过沙箱测试（验证门），才成为技能；
- 接管：新任务与技能签名匹配 → 直接复用（仍要重跑测试确认）；
- **专家叠加**：技能可依赖其他技能（depends_on）——新专家站在旧专家肩上；
  底层技能退役后，上层技能在下次接管验证中自然失效（级联重学，像人的学习）；
- 生命周期：使用统计、成功率；连续失败退役（遗忘=降权，档案保留）。
- 存储：~/.codedojo/skills.json（跨项目持久）。
"""

import json
import re
import time
from pathlib import Path
from typing import Dict, List, Optional

STORE = Path.home() / ".codedojo" / "skills.json"
MATCH_THRESHOLD = 0.42   # 重叠系数阈值（交集/较短方，适合长短不一的任务文本）
JACCARD_FLOOR = 0.42     # Jaccard 下限（严闸：离线无裁判时的唯一防线）
JACCARD_FLOOR_SOFT = 0.25  # 软闸（LLM 裁判可用时：软召回 + 裁判精判）
RETIRE_AFTER_FAILS = 3   # 连续失败 N 次退役
MAX_DEP_DEPTH = 4        # 依赖递归深度上限


# 任务模板停用词：所有编码任务都含的措辞，不构成"同族"证据
STOPWORDS = {
    "写一", "一个", "函数", "附带", "测试", "带测", "实现", "帮我", "完成", "要求",
    "以下", "python", "pytest", "代码", "程序", "编写", "给我", "做一个", "个函",
}


def tokenize(text: str) -> set:
    """中英混合关键词：英文词 + 中文字符 bigram（剔除任务模板停用词）。"""
    tokens = set(t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text)
                 if len(t) >= 2)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.update(cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1))
    return tokens - STOPWORDS


class Skill:
    def __init__(self, data: dict) -> None:
        self.id: str = data["id"]
        self.task: str = data["task"]
        self.files: List[dict] = data["files"]            # [{path, content}]
        self.test_cmd: str = data.get("test_cmd", "python -m pytest -q")
        self.depends_on: List[str] = list(data.get("depends_on", []))  # 依赖的技能 id
        self.capabilities: List[str] = list(data.get("capabilities", []))  # 能力签名（教师生成）
        self.uses: int = data.get("uses", 0)
        self.successes: int = data.get("successes", 0)
        self.fails: int = data.get("fails", 0)
        self.consecutive_fails: int = data.get("consecutive_fails", 0)
        self.retired: bool = data.get("retired", False)
        self.created: float = data.get("created", time.time())
        self._tokens = tokenize(self.task)
        self._cap_tokens = set()
        for cap in self.capabilities:
            self._cap_tokens |= tokenize(cap)

    def to_dict(self) -> dict:
        return {"id": self.id, "task": self.task, "files": self.files,
                "test_cmd": self.test_cmd, "depends_on": self.depends_on,
                "capabilities": self.capabilities,
                "uses": self.uses, "successes": self.successes, "fails": self.fails,
                "consecutive_fails": self.consecutive_fails,
                "retired": self.retired, "created": self.created}

    def module_names(self) -> set:
        """本技能提供的可 import 模块名（顶层 .py 文件去后缀，不含 tests/）。"""
        out = set()
        for f in self.files:
            p = f["path"]
            if not p.startswith("tests/") and "/" not in p and p.endswith(".py"):
                out.add(Path(p).stem)
        return out

    def match_score(self, task_text: str) -> float:
        """重叠系数：|A∩B| / min(|A|,|B|)——任务文本长短不一时比 Jaccard 公平。"""
        other = tokenize(task_text)
        if not other or not self._tokens:
            return 0.0
        inter = len(self._tokens & other)
        if inter < 3:          # 至少 3 个共同关键词
            return 0.0
        return inter / min(len(self._tokens), len(other))

    def jaccard_score(self, task_text: str) -> float:
        """Jaccard：|A∩B| / |A∪B|——惩罚"需求超集"。

        反例（重叠系数的盲区）：技能"罗马数字转整数"（8 个内容词）vs
        任务"批量把一组罗马数字全部转换成整数并求和"（16 个内容词）——
        重叠系数 7/8=0.88 误判同族；Jaccard 7/17=0.41 揭示任务多出
        "批量/一组/求和"等新需求，应交教师而非接管。
        """
        other = tokenize(task_text)
        if not other or not self._tokens:
            return 0.0
        inter = len(self._tokens & other)
        if inter < 3:
            return 0.0
        return inter / len(self._tokens | other)

    def capability_overlap(self, task_text: str) -> bool:
        """能力签名与新任务有内容词相交（注册表过滤用）。"""
        if not self._cap_tokens:
            return True   # 旧技能无签名：不过滤
        return bool(self._cap_tokens & tokenize(task_text))

    def record(self, ok: bool) -> None:
        self.uses += 1
        if ok:
            self.successes += 1
            self.consecutive_fails = 0
        else:
            self.fails += 1
            self.consecutive_fails += 1
            if self.consecutive_fails >= RETIRE_AFTER_FAILS:
                self.retired = True   # 退役：不再参与接管，档案保留


class SkillStore:
    def __init__(self, path: Path = STORE) -> None:
        self.path = path
        self.skills: Dict[str, Skill] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                for item in data:
                    s = Skill(item)
                    self.skills[s.id] = s
            except Exception:
                self.skills = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([s.to_dict() for s in self.skills.values()],
                       ensure_ascii=False, indent=2), encoding="utf-8")

    def mount(self, task: str, files: List[dict], test_cmd: str,
              depends_on: Optional[List[str]] = None,
              capabilities: Optional[List[str]] = None) -> Skill:
        """挂载（调用方须已通过验证门）。同族已有技能 -> 原位升级（依赖取并集）。"""
        deps = list(dict.fromkeys(depends_on or []))
        caps = list(capabilities or [])
        for existing in list(self.skills.values()):
            # 去重合并与接管同一套双闸门：Jaccard 不过 = 能力不同 = 新技能，
            # 绝不能原位覆盖（否则底层技能文件被换，上层依赖者全遭殃）
            if (not existing.retired
                    and existing.match_score(task) >= MATCH_THRESHOLD
                    and existing.jaccard_score(task) >= JACCARD_FLOOR):
                existing.files = files
                existing.test_cmd = test_cmd
                existing.depends_on = list(dict.fromkeys(existing.depends_on + deps))
                if caps:
                    existing.capabilities = caps
                    existing._cap_tokens = set()
                    for cap in caps:
                        existing._cap_tokens |= tokenize(cap)
                existing.consecutive_fails = 0
                self.save()
                return existing
        sid = "skill_{}_{}".format(int(time.time() * 1000), len(self.skills))
        s = Skill({"id": sid, "task": task, "files": files,
                   "test_cmd": test_cmd, "depends_on": deps,
                   "capabilities": caps})
        self.skills[sid] = s
        self.save()
        return s

    def match(self, task_text: str, soft: bool = False) -> Optional[Skill]:
        """最佳匹配技能（非退役、双闸门：重叠系数 + Jaccard 下限）。

        soft=True（LLM 裁判在场）：软闸只做廉价召回，语义精度交给裁判——
        换措辞的真同族任务（Jaccard 0.25~0.42）能进入裁决而非被词面误杀；
        soft=False（离线）：严闸是唯一防线，宁缺勿滥。
        """
        floor = JACCARD_FLOOR_SOFT if soft else JACCARD_FLOOR
        best, best_score = None, 0.0
        for s in self.skills.values():
            if s.retired:
                continue
            sc = s.match_score(task_text)
            if sc < MATCH_THRESHOLD:
                continue
            if s.jaccard_score(task_text) < floor:
                continue
            if sc > best_score:
                best, best_score = s, sc
        return best

    def files_of(self, skill: Skill) -> List[dict]:
        """技能的完整文件集 = 递归依赖文件（先写）+ 自身文件（后写、可覆盖同名）。

        环安全（访问集）+ 深度上限。依赖退役仍返回其文件（档案保留）——
        上层技能接管时测试若因此失败，record(False) 累积到退役，触发级联重学。
        """
        out: List[dict] = []
        seen_paths: set = set()

        def collect(s: Skill, depth: int, visiting: set) -> None:
            if depth > MAX_DEP_DEPTH or s.id in visiting:
                return
            visiting.add(s.id)
            for dep_id in s.depends_on:
                dep = self.skills.get(dep_id)
                if dep is not None:
                    collect(dep, depth + 1, visiting)
            for f in s.files:
                if f["path"] not in seen_paths:
                    seen_paths.add(f["path"])
                    out.append(f)
            visiting.discard(s.id)

        collect(skill, 0, set())
        # 自身文件最后写（覆盖依赖同名）——按写入顺序返回
        own = [f for f in skill.files]
        deps_flat = [f for f in out if f not in own or True]
        # 简化：out 已按依赖先、自身后收集；确保自身在最后
        result = [f for f in out]
        own_paths = {f["path"] for f in own}
        result = [f for f in result if f["path"] not in own_paths] + own
        return result

    def find_by_module(self, module: str) -> Optional[Skill]:
        """按可 import 模块名找提供该模块的（活跃）技能。"""
        for s in self.skills.values():
            if not s.retired and module in s.module_names():
                return s
        return None

    def stats(self) -> dict:
        active = [s for s in self.skills.values() if not s.retired]
        deps = sum(len(s.depends_on) for s in active)
        return {"total": len(self.skills), "active": len(active),
                "retired": len(self.skills) - len(active), "dep_links": deps}
