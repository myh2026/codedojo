"""技能库：验证通过的解法挂载为持久技能（GraphDojo 的"图"）。

- 挂载：解法必须先过沙箱测试（验证门），才成为技能；
- 接管：新任务与技能签名匹配 → 直接复用（仍要重跑测试确认）；
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
RETIRE_AFTER_FAILS = 3   # 连续失败 N 次退役


def tokenize(text: str) -> set:
    """中英混合关键词：英文词 + 中文字符 bigram。"""
    tokens = set(t.lower() for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text) if len(t) >= 2)
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    tokens.update(cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1))
    return tokens


class Skill:
    def __init__(self, data: dict) -> None:
        self.id: str = data["id"]
        self.task: str = data["task"]
        self.files: List[dict] = data["files"]            # [{path, content}]
        self.test_cmd: str = data.get("test_cmd", "python -m pytest -q")
        self.uses: int = data.get("uses", 0)
        self.successes: int = data.get("successes", 0)
        self.fails: int = data.get("fails", 0)
        self.consecutive_fails: int = data.get("consecutive_fails", 0)
        self.retired: bool = data.get("retired", False)
        self.created: float = data.get("created", time.time())
        self._tokens = tokenize(self.task)

    def to_dict(self) -> dict:
        return {"id": self.id, "task": self.task, "files": self.files,
                "test_cmd": self.test_cmd, "uses": self.uses,
                "successes": self.successes, "fails": self.fails,
                "consecutive_fails": self.consecutive_fails,
                "retired": self.retired, "created": self.created}

    def match_score(self, task_text: str) -> float:
        """重叠系数：|A∩B| / min(|A|,|B|)——任务文本长短不一时比 Jaccard 公平。"""
        other = tokenize(task_text)
        if not other or not self._tokens:
            return 0.0
        inter = len(self._tokens & other)
        if inter < 3:          # 至少 3 个共同关键词
            return 0.0
        return inter / min(len(self._tokens), len(other))

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

    def mount(self, task: str, files: List[dict], test_cmd: str) -> Skill:
        """挂载（调用方须已通过验证门）。同族已有技能 -> 原位升级（去重合并）。"""
        for existing in list(self.skills.values()):
            if not existing.retired and existing.match_score(task) >= MATCH_THRESHOLD:
                existing.files = files
                existing.test_cmd = test_cmd
                existing.consecutive_fails = 0
                self.save()
                return existing
        sid = "skill_{}_{}".format(int(time.time() * 1000), len(self.skills))
        s = Skill({"id": sid, "task": task, "files": files, "test_cmd": test_cmd})
        self.skills[sid] = s
        self.save()
        return s

    def match(self, task_text: str) -> Optional[Skill]:
        """最佳匹配技能（非退役、分数过阈值）。"""
        best, best_score = None, 0.0
        for s in self.skills.values():
            if s.retired:
                continue
            sc = s.match_score(task_text)
            if sc > best_score:
                best, best_score = s, sc
        if best is not None and best_score >= MATCH_THRESHOLD:
            return best
        return None

    def stats(self) -> dict:
        active = [s for s in self.skills.values() if not s.retired]
        return {"total": len(self.skills), "active": len(active),
                "retired": len(self.skills) - len(active)}
