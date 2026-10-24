# CodeDojo 蒸馏战役规程（deepseek-v4.1-flash-1017）

教师模型：`DEEPSEEK_MODEL=deepseek-flash`（API ID；服务端版本 DeepSeek-V4.1-Flash-1017，
多模态 MoE，1M 上下文）。执行环境：uv（`.python-version` 3.12，`uv sync --extra desktop`）。

## 定价与预算（峰时价，USD/百万 token）

| 输入 cache-miss | 输入 cache-hit | 输出 |
|:---:|:---:|:---:|
| $0.30 | $0.006 | $1.20 |

- **预算硬闸**：战役默认 $2.00，每次 API 调用前检查累计 `cost_usd`，超限立即熔断。
- **缓存策略**：SYSTEM_PROMPT 前缀稳定 → 重复生成/裁判调用吃 cache-hit（50 倍价差）；
  账本分开计 `tokens_in_hit / tokens_in_miss`。
- **thinking 策略**：生成调用开 thinking（默认，reasoning 计入 max_tokens=16384）；
  裁判调用关 thinking + max_tokens=2048（省钱提速）。
- 全战役预估成本 **<$0.15**（12 教学任务 × ~3k in / 1.5k out + 若干轻量裁判）。

## 七阶段

| 阶段 | 内容 | 通过判据 | 关键指标 |
|:---|:---|:---|:---|
| P0 自检 | 1 次模型 ping | 返回 JSON | 连通性、服务版本回显 |
| P1 教学 | 12 任务族各 1 轮 生成→沙箱验证→挂载 | 测试全过 + HSL 契约 pass | 生成调用、修复迭代、tokens、成本 |
| P2 换措辞 | 同 12 族换措辞复跑 | Dice 软闸+裁判放行 → 技能接管 | **零生成接管率** |
| P3 叠加 | 4 个组合任务（预期 import 已挂专家） | 验证过 + depends_on ≥ 1 | 新增依赖边 |
| P4 保留集 | 4 个全新族（从未教过） | **零误接管** + 教师可解 | 防过度泛化金标准 |
| P5 蒸馏对照 | 3 族：纯教师直解 vs 技能接管 | 双路径都过测试 | 延迟比、成本比 |
| P6 报告 | 汇总落盘 `distill_campaign_results.{md,json}` | — | 全指标 + 总成本 + 缓存命中率 |

### P5 对照的意义

同一任务两种执行路径：教师直解（干净沙箱、无技能库）vs 技能接管（零生成调用）。
这是"蒸馏收益"的直接量化——预期接管路径 ~2s/$0.000x，教师路径 ~10s/$0.00x。

## 任务族课程表

教学 12 族：词频 / 闰年 / 回文 / 罗马数字 / 温度转换 / 素数 / 单词反转 /
FizzBuzz / 去重保序 / 阶乘 / base64 编解码 / 最大公约数与最小公倍数。
组合 4 个：最高频单词（复用词频）、某年 2 月天数（复用闰年）、批量罗马求和
（复用罗马）、词频表格式化输出（复用词频）。
保留 4 族（战役内首次出现）：凯撒密码、ISBN 校验、尼科彻斯定理验证、括号匹配。

## 失败处置

- 生成 3 轮修复不过 → 该族记失败，战役继续（不熔断）；
- 裁判不可用（协议失败）→ 失败放行（降级为纯词面闸门），日志标注；
- 网络抖动 → LLM 内建重试 ×2；战役逐阶段落盘，重跑可从断点续。

## 复现

```bash
uv sync --extra desktop
DEEPSEEK_API_KEY=sk-... uv run python demos/distill_campaign.py          # 完整战役
DEEPSEEK_API_KEY=sk-... uv run python demos/distill_campaign.py --budget 0.5   # 小预算
```
