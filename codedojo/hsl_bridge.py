"""HSL 桥：技能 -> .hsl 契约 + dhv-ts check 验证门。

每个挂载的技能（= 一个"专业"）序列化为一个自包含 HSL 模块：
  - 拓扑：implement -> verify -> report（带预算闸门的 AgentLoop）；
  - 能力属性：#[capability(...)]（对齐 HSL 编译期能力声明）；
  - 契约通过 `dhv-ts check` 校验（工具链可用时；不可用则记录 skipped）。

工具链发现顺序：
  1. 环境变量 CODEDOJO_HSL_ROOT（指向 HSL 仓库根，含 toolchain/dhv-ts）；
  2. 常见路径 D:\\GraphDojo\\vendor\\hsl。
"""

import re
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

CONTRACT_DIR = Path.home() / ".codedojo" / "skills_hsl"

_CANDIDATES = [
    Path("D:/GraphDojo/vendor/hsl"),
    Path.home() / "GraphDojo" / "vendor" / "hsl",
]


def find_hsl_root() -> Optional[Path]:
    env = shutil.os.environ.get("CODEDOJO_HSL_ROOT")
    if env:
        p = Path(env)
        if (p / "toolchain" / "dhv-ts" / "src" / "main.ts").exists():
            return p
    for p in _CANDIDATES:
        if (p / "toolchain" / "dhv-ts" / "src" / "main.ts").exists():
            return p
    return None


def find_bun() -> Optional[str]:
    for cand in (shutil.which("bun"), str(Path.home() / ".bun" / "bin" / "bun.exe"),
                 str(Path.home() / ".bun" / "bin" / "bun")):
        if cand and Path(cand).exists():
            return cand
    return None


def _pascal(skill_id: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", skill_id)
    name = "".join(p.capitalize() for p in parts if not p.isdigit()) or "Skill"
    return name


def _clean(text: str, limit: int = 160) -> str:
    return (text.replace("\\", "/").replace('"', "'")
            .replace("\n", " ").replace("\r", " ").strip()[:limit])


def skill_to_hsl(skill) -> str:
    """技能 -> 可通过 dhv-ts check 的 HSL 契约文本（拓扑/能力/验证说明）。"""
    pascal = _pascal(skill.id)
    lines: List[str] = []
    lines.append("// ============================================================================")
    lines.append("// {}.hsl — CodeDojo 技能契约（自动生成，请勿手改）".format(skill.id))
    lines.append("// 任务: {}".format(_clean(skill.task)))
    lines.append("// 产物: {}".format(", ".join(f["path"] for f in skill.files)))
    lines.append("// 验证: {}（沙箱 pytest 已通过后才允许挂载）".format(_clean(skill.test_cmd)))
    if getattr(skill, "depends_on", None):
        lines.append("// 依赖（专家叠加）: {}".format(", ".join(skill.depends_on)))
    lines.append("// ============================================================================")
    lines.append("")
    lines.append("export struct {}State {{".format(pascal))
    lines.append("    task: String,")
    lines.append("    steps: i64,")
    lines.append("    summary: String,")
    lines.append("}")
    lines.append("")
    lines.append("export enum Signal {")
    lines.append("    Proceed { note: String },")
    lines.append("    Done { summary: String },")
    lines.append("    Failed { reason: String },")
    lines.append("}")
    lines.append("")
    lines.append("fn step_at(i: i64) -> Signal {")
    steps = ["implement", "verify", "report"]
    for idx, name in enumerate(steps):
        kw = "if" if idx == 0 else "else if"
        lines.append("    {} i == {} {{".format(kw, idx))
        lines.append("        Signal::Proceed {{ note: String::from(\"{}\") }}".format(name))
        lines.append("    }")
    lines.append("    else {")
    lines.append("        Signal::Done { summary: String::from(\"(由沙箱执行)\") }")
    lines.append("    }")
    lines.append("}")
    lines.append("")
    lines.append("#[capability(exec_pytest)]")
    lines.append("graph {}(mut state: {}State) -> {}State {{".format(pascal, pascal, pascal))
    for idx, name in enumerate(steps):
        lines.append("    node {}: String = String::from(\"{}\");".format(name, name))
    lines.append("")
    lines.append("    edge implement -> verify on Signal::Proceed;")
    lines.append("    edge verify -> report on Signal::Proceed;")
    lines.append("")
    lines.append("    loop {")
    lines.append("        if state.steps >= 8 {")
    lines.append("            break;")
    lines.append("        }")
    lines.append("        match step_at(state.steps) {")
    lines.append("            Signal::Proceed { note } => {")
    lines.append("                println!(\"[{}] step {{}}: {{}}\", state.steps, note);".format(skill.id[-8:]))
    lines.append("                state.steps += 1;")
    lines.append("            },")
    lines.append("            Signal::Done { summary } => {")
    lines.append("                state.summary = summary;")
    lines.append("                break;")
    lines.append("            },")
    lines.append("            Signal::Failed { reason } => {")
    lines.append("                state.summary = reason;")
    lines.append("                break;")
    lines.append("            },")
    lines.append("        }")
    lines.append("    }")
    lines.append("    state")
    lines.append("}")
    lines.append("")
    lines.append("scale = microkernel;")
    lines.append("")
    return "\n".join(lines)


def write_contract(skill) -> dict:
    """技能契约落盘；工具链可用时跑 dhv-ts check。返回 {path, check, detail}。"""
    CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
    path = CONTRACT_DIR / "{}.hsl".format(skill.id)
    text = skill_to_hsl(skill)
    path.write_text(text, encoding="utf-8")

    root = find_hsl_root()
    bun = find_bun()
    if root is None or bun is None:
        return {"path": str(path), "check": "skipped",
                "detail": "HSL 工具链不可用（设 CODEDOJO_HSL_ROOT 指向 HSL 仓库）"}
    main = root / "toolchain" / "dhv-ts" / "src" / "main.ts"
    try:
        proc = subprocess.run([bun, str(main), "check", str(path)],
                              capture_output=True, text=True, timeout=60)
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == 0 and "0 error" in out
        return {"path": str(path), "check": "pass" if ok else "fail",
                "detail": out.strip().splitlines()[-1] if out.strip() else ""}
    except Exception as exc:
        return {"path": str(path), "check": "error", "detail": str(exc)}
