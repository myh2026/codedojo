"""CodeDojo 桌面层：系统托盘常驻 + 任务窗口 + 完成通知（Windows）。

架构：
  主线程  tkinter 主循环（任务窗口 / 历史窗口）
  后台线程 pystray 托盘图标（菜单：新任务 / 历史 / 退出）
  工作线程 Agent.run_task（不阻塞 UI）
  通信      queue + after() 轮询（Tk 只允许主线程改 UI）

用法：python -m codedojo.desktop
"""

import json
import queue
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path

from codedojo.agent import Agent
from codedojo.llm import LLM
from codedojo.skills import SkillStore

HISTORY = Path.home() / ".codedojo" / "history.json"
APP_NAME = "CodeDojo"


def make_icon_image():
    """用 PIL 画一个简单的橙色道场图标。"""
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (24, 26, 32, 255))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([6, 6, 58, 58], radius=12, fill=(245, 158, 11, 255))
    d.rectangle([24, 24, 40, 40], fill=(24, 26, 32, 255))
    d.rectangle([29, 16, 35, 48], fill=(24, 26, 32, 255))
    d.rectangle([16, 29, 48, 35], fill=(24, 26, 32, 255))
    return img


def load_history() -> list:
    if HISTORY.exists():
        try:
            return json.loads(HISTORY.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def append_history(entry: dict) -> None:
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    hist = load_history()
    hist.insert(0, entry)
    HISTORY.write_text(json.dumps(hist[:200], ensure_ascii=False, indent=2),
                       encoding="utf-8")


class App:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.withdraw()                      # 只有任务窗口可见，主窗口常驻托盘
        self.q: "queue.Queue[str]" = queue.Queue()
        self.tray = None
        self._setup_tray()
        self.root.after(200, self._drain)

    # ------------------------------------------------------------------ 托盘
    def _setup_tray(self) -> None:
        import pystray
        menu = pystray.Menu(
            pystray.MenuItem("新任务…", self._on_new_task, default=True),
            pystray.MenuItem("历史", self._on_history),
            pystray.MenuItem("技能库", self._on_skills),
            pystray.MenuItem("退出", self._on_quit),
        )
        self.tray = pystray.Icon(APP_NAME, make_icon_image(), APP_NAME, menu)
        threading.Thread(target=self.tray.run, daemon=True).start()

    def _notify(self, title: str, message: str) -> None:
        try:
            self.tray.notify(title, message)
        except Exception:
            pass

    # ------------------------------------------------------------------ 菜单动作
    def _on_new_task(self, *_):
        self.root.after(0, self._open_task_window)

    def _on_history(self, *_):
        self.root.after(0, self._open_history)

    def _on_skills(self, *_):
        self.root.after(0, self._open_skills)

    def _on_quit(self, *_):
        self.root.after(0, self._shutdown)

    def _shutdown(self):
        try:
            self.tray.stop()
        except Exception:
            pass
        self.root.destroy()

    # ------------------------------------------------------------------ 任务窗口
    def _open_task_window(self):
        win = tk.Toplevel(self.root)
        win.title("CodeDojo · 新任务")
        win.geometry("620x420")
        tk.Label(win, text="任务描述：").pack(anchor="w", padx=10, pady=(10, 0))
        text = tk.Text(win, height=5, wrap="word")
        text.pack(fill="both", expand=True, padx=10)

        tk.Label(win, text="运行日志：").pack(anchor="w", padx=10)
        log = tk.Text(win, height=12, state="disabled", wrap="word")
        log.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        def append_log(msg):
            log.configure(state="normal")
            log.insert("end", msg + "\n")
            log.see("end")
            log.configure(state="disabled")

        state = {"running": False}

        def worker(task):
            agent = Agent(LLM(), SkillStore(), log=lambda m: self.q.put(m))
            t0 = time.time()
            try:
                r = agent.run_task(task)
            except Exception as exc:
                class R:  # 极简失败结果
                    ok = False; source = "error"; error = str(exc)
                    llm_calls = 0; elapsed_ms = 0
                r = R()
            append_history({
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "task": task, "ok": bool(r.ok), "source": getattr(r, "source", "?"),
                "elapsed_ms": round(getattr(r, "elapsed_ms", 0)),
                "llm_calls": getattr(r, "llm_calls", 0),
                "skill_id": getattr(r, "skill_id", ""),
                "files": [f["path"] for f in getattr(r, "files", [])],
            })
            self.q.put("[done] ok={} source={} llm={} 用时{:.0f}s".format(
                r.ok, r.source, r.llm_calls, time.time() - t0))
            self._notify(APP_NAME, "任务{}：{}".format(
                "完成" if r.ok else "失败", task[:40]))
            state["running"] = False

        def on_run():
            task = text.get("1.0", "end").strip()
            if not task or state["running"]:
                return
            state["running"] = True
            append_log("[dojo] 任务：{}".format(task))
            threading.Thread(target=worker, args=(task,), daemon=True).start()

        bar = tk.Frame(win)
        bar.pack(fill="x", padx=10, pady=8)
        tk.Button(bar, text="运行 (Enter)", command=on_run).pack(side="left")
        tk.Button(bar, text="关闭", command=win.destroy).pack(side="right")
        text.bind("<Control-Return>", lambda e: on_run())

    # ------------------------------------------------------------------ 历史 / 技能
    def _open_history(self):
        win = tk.Toplevel(self.root)
        win.title("CodeDojo · 历史")
        win.geometry("680x400")
        tk.Label(win, text="最近任务（双击查看详情文件）").pack(anchor="w", padx=10, pady=8)
        lb = tk.Listbox(win)
        lb.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        for h in load_history()[:100]:
            lb.insert("end", "[{}] {} ok={} {} llm={}".format(
                h.get("time", "")[:16], h.get("task", "")[:44],
                h.get("ok"), h.get("source"), h.get("llm_calls")))

        def open_detail(_event):
            idx = lb.curselection()
            if not idx:
                return
            entry = load_history()[idx[0]]
            win2 = tk.Toplevel(win)
            win2.title("任务详情")
            txt = tk.Text(win2, wrap="word")
            txt.pack(fill="both", expand=True)
            txt.insert("end", json.dumps(entry, ensure_ascii=False, indent=2))

        lb.bind("<Double-Button-1>", open_detail)

    def _open_skills(self):
        win = tk.Toplevel(self.root)
        win.title("CodeDojo · 技能库")
        win.geometry("680x400")
        store = SkillStore()
        info = store.stats()
        tk.Label(win, text="技能 {} 个（活跃 {} / 退役 {}）——验证过的解法，同族任务零 LLM 接管".format(
            info["total"], info["active"], info["retired"])).pack(anchor="w", padx=10, pady=8)
        lb = tk.Listbox(win)
        lb.pack(fill="both", expand=True, padx=10, pady=(0, 8))
        for s in store.skills.values():
            lb.insert("end", "[{}] {} uses={} 成功率{:.0%}{}".format(
                s.id[-6:], s.task[:40], s.uses,
                s.successes / max(1, s.uses), "（退役）" if s.retired else ""))

    # ------------------------------------------------------------------ 日志泵
    def _drain(self):
        try:
            while True:
                msg = self.q.get_nowait()
                for win in self.root.winfo_children():
                    if isinstance(win, tk.Toplevel) and win.title().endswith("新任务"):
                        for child in win.winfo_children():
                            if isinstance(child, tk.Text):
                                child.configure(state="normal")
                                child.insert("end", msg + "\n")
                                child.see("end")
                                child.configure(state="disabled")
                                break
                        break
        except queue.Empty:
            pass
        self.root.after(200, self._drain)

    def run(self):
        self.root.mainloop()


def main() -> int:
    app = App()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
