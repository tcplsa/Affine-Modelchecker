# 2026-11-02 研究快照

这个快照保存当前仍有复用价值、适合 Git 托管的小型材料：

- `compare/`：仿射/XOR/PDR 的分析、运行和数据筛选源码，外加顶层技术报告与小型配置；
- `circuit_reports/`：whole-core、lemma 质量、模块拆分和网表研究报告；
- `wide_adder_decomposition/`：64 位分块进位合同与整体溢出性质的教学示例。

快照有意排除：

- HWMCC 原始模型；
- `compare/results/` 的大规模运行体；
- whole-core 和 LLM workflow 的大 trace；
- 已构建二进制、求解器输出、CNF、AIG、VCD 和临时文件。

这些排除项体积大且多数可由本快照中的脚本、公开基准和原工程重新生成。旧实验的关键结论保留在报告、顶层 JSON 配置和本地维护归档中。

`wide_adder_decomposition/run.sh` 在固定工具路径存在时检查：整体一拍延迟加法性质、四个 16 位局部进位合同，以及 Lean 组合定理。它是方法解释样例，不是拆分性能优势结论。
