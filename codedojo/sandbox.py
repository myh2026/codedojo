"""沙箱：每任务独立工作区 + 带超时的命令执行。"""

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

WORK_ROOT = Path.home() / ".codedojo" / "work"
DEFAULT_TIMEOUT = 90


class Sandbox:
    def __init__(self, task_id: str) -> None:
        WORK_ROOT.mkdir(parents=True, exist_ok=True)
        self.dir = WORK_ROOT / task_id
        if self.dir.exists():
            shutil.rmtree(self.dir)
        self.dir.mkdir(parents=True)

    def write_files(self, files: List[dict]) -> None:
        for f in files:
            path = self.dir / f["path"]
            # 防路径逃逸：只允许沙箱内相对路径
            resolved = path.resolve()
            if not str(resolved).startswith(str(self.dir.resolve())):
                raise ValueError("非法文件路径: {}".format(f["path"]))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f["content"], encoding="utf-8")

    def run(self, cmd: str, timeout: int = DEFAULT_TIMEOUT) -> dict:
        """执行命令（cwd=沙箱）。返回 {ok, stdout, stderr, returncode}。"""
        try:
            proc = subprocess.run(
                cmd, shell=True, cwd=str(self.dir),
                capture_output=True, text=True, timeout=timeout)
            return {"ok": proc.returncode == 0,
                    "stdout": (proc.stdout or "")[-8000:],
                    "stderr": (proc.stderr or "")[-8000:],
                    "returncode": proc.returncode}
        except subprocess.TimeoutExpired:
            return {"ok": False, "stdout": "", "stderr": "超时（{}s）".format(timeout),
                    "returncode": -1}

    def cleanup(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)
