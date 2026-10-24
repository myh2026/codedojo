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

## 快速开始（uv）

```bash
uv sync --extra desktop

# CLI 模式（默认教师 deepseek-flash = DeepSeek-V4.1-Flash-1017）
set DEEPSEEK_API_KEY=sk-...
uv run python -m codedojo.cli "写一个函数统计文本文件词频，附带 pytest 测试"

# 桌面模式（托盘常驻）
uv run python -m codedojo.desktop

# 离线测试（无需 API key，33 项）
uv run pytest tests/

# 换教师模型
set DEEPSEEK_MODEL=deepseek-flash   # 或任意可用模型 ID
```

## 蒸馏战役（distill_campaign）

七阶段全流程战役（规程见 [docs/DISTILL_PLAN.md](docs/DISTILL_PLAN.md)）：
教学 12 族 → 换措辞接管 → 组合叠加 → 保留集（防误接管金标准）→
教师/技能双路径对照 → 成本与缓存命中率账本。预算硬闸默认 $2。

```bash
DEEPSEEK_API_KEY=sk-... uv run python demos/distill_campaign.py
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

## 防误接管三道防线（实测拦截"单转换技能接管批量求和任务"）

1. **双闸门（词面层）**：重叠系数 ≥ 0.42 召回同族 + Jaccard 下限惩罚
   "需求超集"（任务比技能多出批量/求和等新要求时词面重合度必然被稀释）；
   LLM 在场时软闸（0.25）只做召回、精度交给裁判；离线严闸是唯一防线；
2. **能力裁判（语义层）**：接管前一次轻量 LLM 调用（~170 token），判定
   技能的**能力签名**（教师挂载时生成的 capabilities）是否覆盖任务全部
   要求；失败放行（离线/降级不阻塞接管）；
3. **验证门（功能层）**：接管仍要带依赖重跑技能自身 pytest——技能坏了
   依然进教师重学。

同轮修复的配套问题：`mount()` 去重合并与接管同一套双闸门（此前批量解法
会原位覆盖单转换技能的文件、殃及全部上层依赖者）；依赖只认**代码实际
import 的地面真值**（教师声明但不 import 的不入库）；专家注册表按能力
相关性过滤（词频专家不进闰年任务的注册表，从源头减少冗余复用）。

## 诚实边界

- 只生成 Python + pytest 形态的小型任务解法；不含多文件工程级重构；
- 接管的"零 LLM"精确定义：**零代码生成调用**；LLM 在场时有至多一次
  轻量裁判（~170 token / ~1s，记账在任务结果里），离线时完全零调用；
- 词面匹配仍是统计召回：极端换措辞（词面重合 < 0.25）仍会漏配走教师
  （多花一次生成调用，不出错）；裁判自身是 LLM，可能误判（失败放行
  偏向可用性）；
- 生成的代码在沙箱内以当前用户权限运行（有路径防护、无系统级沙箱）；
- LLM 单步决策质量决定首次成功率（修复回路兜底 ≤3 轮）。
