# CodeDojo · 桌面编码智能体

GraphDojo 血统的桌面 coding agent：**LLM 规划写码 → 沙箱验证 → 技能挂载 → 同族任务零 LLM 接管**。

```
任务（自然语言）
  ├─ 技能库匹配 ──── 命中 → 沙箱重验 → 通过 → 直接交付（零 LLM，毫秒级）
  └─ 未命中 ─────── DeepSeek 生成（实现 + pytest 测试）
                      → 沙箱运行测试
                      → 失败回喂修复（≤3 轮）
                      → 通过 → 挂载为技能（验证门后的持久记忆）
```

## 所有专业装进一个 AI（专家叠加，像人的学习）

技能库就是"专业"的集合——每个验证过的解法是一门手艺，新专家可以**站在旧专家肩上**：

- **教师看得见专家**：生成时注入已挂载专家清单（模块源码），LLM 可直接 `import` 复用
  而不是重写——新技能通过 `depends_on` 记录依赖（代码实际 import 的地面真值 + 声明）；
- **组合即时验证**：依赖文件自动落沙箱，组合解法在同一轮测试里跑通才挂载；
- **级联重学**：底层专家退役（被证伪）后，上层技能下次接管时验证自然失败 →
  走教师重学——"基础错了要重学上层"，无需专门失效传播（验证门即传播机制）。

实测学习链（真实 DeepSeek）：`roman_to_int`（新专家，2 轮过验）→
`roman_sum`（**import 复用前者，依赖入库**，1 轮过验）→ 同族换措辞零 LLM 接管。

## HSL 契约门（对齐 GraphDojo 的 .hsl 验证）

每个挂载技能自动生成一份 HSL 契约（`~/.codedojo/skills_hsl/<skill_id>.hsl`）：
implement → verify → report 三节点拓扑 + `#[capability]` 属性 + 依赖标注，
经 `dhv-ts check` 真实校验（工具链不可用则记录 skipped，契约仍落盘）。
CodeDojo 主循环本身也自举为 HSL harness（`harness/codedojo.hsl`，
剧本驱动的教师→验证→挂载→接管循环，过 check 且可 run）。

## 特性

- **验证门**：任何解法必须先过自己生成的 pytest 才被接受/挂载；
- **技能接管**：同族任务命中技能 → 带依赖重验 → 零 LLM 调用；
- **技能生命周期**：使用统计、连续失败 3 次自动退役（档案保留，可复活）；
- **沙箱**：每任务独立工作区、路径逃逸防护、命令超时；
- **桌面常驻**：系统托盘图标（新任务/历史/技能库/退出）、任务窗口实时日志、完成通知；
- **CLI 同引擎**：`python -m codedojo.cli "任务"` 无头使用；
- **成本可观测**：每次任务报告 LLM 调用数与 token。

## 快速开始

```bash
pip install openai pystray pillow pytest

# CLI 模式
set DEEPSEEK_API_KEY=sk-...
python -m codedojo.cli "写一个函数统计文本文件词频，附带 pytest 测试"

# 桌面模式（托盘常驻）
python -m codedojo.desktop

# 离线测试（无需 API key，19 项）
python -m pytest tests/
```

数据目录：`~/.codedojo/`（skills.json 技能库与依赖 / skills_hsl/ HSL 契约 /
history.json 历史 / work/ 沙箱）。HSL 工具链发现：环境变量 `CODEDOJO_HSL_ROOT`
（指向 HSL 仓库根）或默认 `D:\GraphDojo\vendor\hsl`。

## 与 GraphDojo 的对应

| GraphDojo | CodeDojo |
|:---|:---|
| LLM 教师 | DeepSeek 生成实现+测试 |
| 隔离区验证门 | 沙箱 pytest 必须通过 |
| 挂载 | 技能入库（skills.json + .hsl 契约） |
| 图接管 | 技能命中 → 零 LLM |
| 递归分解（sub:） | 技能依赖（depends_on，import 复用） |
| 遗忘/退役 | 连续失败 3 次退役（级联重学） |
| 判分 | 测试通过即判分 |

## 诚实边界

- 只生成 Python + pytest 形态的小型任务解法；不含多文件工程级重构；
- **重叠匹配可过度泛化**：措辞相近但能力不覆盖的任务可能被误接管
  （如"单转换"技能接管"批量求和"任务）——验证门只重验技能自身测试，
  不判定任务相关性；任务相关性探针（从任务生成验收用例）是下一步；
- 教师可能声明/产生**跨族冗余依赖**（注册表注入后倾向复用不相关专家），
  地面真值 import 提取缓解但不消除；
- 技能匹配是关键词级（中英混合 token + 模板停用词），复杂语义等价可能漏配；
- 生成的代码在沙箱内以当前用户权限运行（有路径防护、无系统级沙箱）；
- LLM 单步决策质量决定首次成功率（修复回路兜底 ≤3 轮）。
