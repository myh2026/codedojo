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

## 特性

- **验证门**：任何解法必须先过自己生成的 pytest 才被接受/挂载；
- **技能接管**：同族任务命中技能 → 重验 → 零 LLM 调用（离线测试锁定该主张）；
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

# 离线测试（无需 API key）
python -m pytest tests/
```

数据目录：`~/.codedojo/`（skills.json 技能库 / history.json 历史 / work/ 沙箱）。

## 与 GraphDojo 的对应

| GraphDojo | CodeDojo |
|:---|:---|
| LLM 教师 | DeepSeek 生成实现+测试 |
| 隔离区验证门 | 沙箱 pytest 必须通过 |
| 挂载 | 技能入库（skills.json） |
| 图接管 | 技能命中 → 零 LLM |
| 遗忘/退役 | 连续失败 3 次退役 |
| 判分 | 测试通过即判分 |

## 诚实边界

- 只生成 Python + pytest 形态的小型任务解法；不含多文件工程级重构；
- 技能匹配是关键词级（中英混合 token），复杂语义等价任务可能漏配；
- 生成的代码在沙箱内以当前用户权限运行（有路径防护、无系统级沙箱）；
- LLM 单步决策质量决定首次成功率（修复回路兜底 ≤3 轮）。
