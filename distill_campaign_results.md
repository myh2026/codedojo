# 蒸馏战役结果（deepseek-flash = DeepSeek-V4.1-Flash-1017）

| 阶段 | 族 | 任务 | 来源 | 成功 | 生成调用 | 成本$ | 秒 | 依赖 | 契约 |
|:--|:--|:--|:--|:--|--:|--:|--:|--:|:--|
| teach | word_freq | 写一个函数统计一段英文文本里每个单词的出现次数（不区分大小写），附带 pytest 测试 | llm | True | 1 | 0.00574 | 45.56 | 0 | pass |
| teach | leap | 写一个函数判断输入年份是否为闰年，附带 pytest 测试 | llm | True | 1 | 0.00187 | 31.57 | 0 | pass |
| teach | palindrome | 写一个函数判断字符串是否为回文（忽略大小写和空格），附带 pytest 测试 | llm | True | 2 | 0.00544 | 38.75 | 0 | pass |
| teach | roman | 写一个函数把罗马数字字符串转换成整数，附带 pytest 测试 | llm | True | 1 | 0.00471 | 40.67 | 0 | pass |
| teach | temp | 写一个函数把摄氏温度转换为华氏温度，附带 pytest 测试 | llm | True | 2 | 0.00996 | 77.79 | 0 | pass |
| teach | prime | 写一个函数判断一个整数是否为素数，附带 pytest 测试 | llm | True | 1 | 0.00530 | 30.63 | 0 | pass |
| teach | reverse | 写一个函数反转字符串中的单词顺序，附带 pytest 测试 | llm | True | 1 | 0.00369 | 22.93 | 0 | pass |
| teach | fizzbuzz | 写一个函数对 1 到 n 做 FizzBuzz（3 的倍数 Fizz、5 的倍数 Buzz、 | llm | True | 1 | 0.00328 | 33.17 | 0 | pass |
| teach | dedupe | 写一个函数去除列表中的重复元素并保持原顺序，附带 pytest 测试 | llm | True | 1 | 0.00476 | 28.17 | 0 | pass |
| teach | factorial | 写一个函数计算阶乘（大数用迭代），附带 pytest 测试 | llm | True | 1 | 0.00261 | 21.5 | 0 | pass |
| teach | base64 | 写一个函数对字符串做 base64 编码和解码两个函数，附带 pytest 测试 | llm | True | 2 | 0.01102 | 70.75 | 0 | pass |
| teach | gcd | 写两个函数分别求最大公约数和最小公倍数，附带 pytest 测试 | llm | True | 1 | 0.00358 | 33.64 | 0 | pass |
| rephrase | word_freq | 统计单词出现次数的函数，带测试 | skill | True | 1 | 0.00008 | 12.67 | 0 | - |
| rephrase | leap | 判断闰年的函数，带测试 | llm | True | 1 | 0.00254 | 22.86 | 1 | pass |
| rephrase | palindrome | 回文判断函数，带测试 | llm | True | 1 | 0.00501 | 28.69 | 1 | pass |
| rephrase | roman | 罗马数字转整数的函数，带测试 | skill | True | 1 | 0.00007 | 5.39 | 0 | - |
| rephrase | temp | 摄氏度转华氏度的函数，带测试 | llm | True | 1 | 0.00814 | 31.9 | 1 | pass |
| rephrase | prime | 素数判断函数，带测试 | skill | True | 1 | 0.00010 | 5.89 | 0 | - |
| rephrase | reverse | 把字符串里单词倒序排列的函数，带测试 | llm | True | 2 | 0.00744 | 31.18 | 1 | pass |
| rephrase | fizzbuzz | FizzBuzz 函数，带测试 | llm | True | 1 | 0.00588 | 23.23 | 1 | pass |
| rephrase | dedupe | 列表去重保序函数，带测试 | llm | True | 1 | 0.00593 | 33.32 | 1 | pass |
| rephrase | factorial | 阶乘计算函数，带测试 | llm | True | 1 | 0.00305 | 29.8 | 1 | pass |
| rephrase | base64 | base64 编码解码函数，带测试 | skill | True | 1 | 0.00008 | 12.85 | 0 | - |
| rephrase | gcd | 最大公约数最小公倍数函数，带测试 | skill | True | 1 | 0.00010 | 12.24 | 0 | - |
| composite | top_word | 写一个函数找一段英文文本中出现次数最多的单词（可复用已挂载专家模块），附带 pytest 测 | llm | True | 1 | 0.00347 | 33.81 | 1 | pass |
| composite | feb_days | 写一个函数返回某年份 2 月的天数（可复用已挂载专家模块），附带 pytest 测试 | llm | True | 2 | 0.00282 | 30.98 | 1 | pass |
| composite | roman_batch | 写一个函数把一组罗马数字全部转换成整数并求和（可复用已挂载专家模块），附带 pytest 测 | llm | True | 2 | 0.00586 | 37.35 | 1 | pass |
| composite | freq_table | 写一个函数把文本词频输出成『单词:次数』逗号分隔的字符串（可复用已挂载专家模块），附带 py | llm | True | 2 | 0.00362 | 26.99 | 1 | pass |
| holdout | caesar | 写一个函数对字符串做凯撒密码加密（位移 3），附带 pytest 测试 | llm | True | 1 | 0.00549 | 32.11 | 0 | pass |
| holdout | isbn | 写一个函数校验 ISBN-10 号码是否合法，附带 pytest 测试 | llm | True | 2 | 0.01312 | 77.91 | 0 | pass |
| holdout | nicomachus | 写一个函数验证尼科彻斯定理：任一整数的立方等于连续奇数之和，返回这些奇数，附带 pytest | llm | True | 1 | 0.01161 | 58.56 | 0 | pass |
| holdout | brackets | 写一个函数判断括号字符串是否匹配（含 ()[]{} 三种），附带 pytest 测试 | llm | True | 1 | 0.00411 | 18.3 | 0 | pass |
| duel_skill | word_freq/skill | 统计单词出现次数的函数，带测试 | skill | True | 1 | 0.00008 | 14.86 | 0 | - |
| duel_teacher | word_freq/teacher | 统计单词出现次数的函数，带测试 | llm | True | 1 | 0.00219 | 22.85 | 0 | pass |
| duel_skill | roman/skill | 罗马数字转整数的函数，带测试 | skill | True | 1 | 0.00007 | 13.36 | 0 | - |
| duel_teacher | roman/teacher | 罗马数字转整数的函数，带测试 | llm | True | 1 | 0.00379 | 29.11 | 0 | pass |
| duel_skill | prime/skill | 素数判断函数，带测试 | skill | True | 1 | 0.00010 | 11.64 | 0 | - |
| duel_teacher | prime/teacher | 素数判断函数，带测试 | llm | True | 1 | 0.00351 | 24.07 | 0 | pass |

## 汇总

- 换措辞零生成接管率：**42%**（5/12；未接管者走教师重挂载，下次即接管）
- 保留集误接管率：**0%**（4 个全新族全部正确交教师）
- 组合叠加（依赖≥1）：**4/4**
- 任务成功：**38/38**
- 总成本：**$0.1695**（缓存命中率 21.9%）
- **蒸馏对照**：教师 25.3s/$0.00316 vs 技能 13.3s/$0.00008 → **延迟 1.9× / 成本 38.4×**（3 族均值）

注：P5 对照阶段因脚本缺陷断点续跑于第二进程，总成本为两段之和；各行数据均为真实测量。技能路径秒数含沙箱 pytest 重验（约 5-13s），纯决策时间远低于此。
