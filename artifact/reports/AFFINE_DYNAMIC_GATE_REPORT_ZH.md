# 仿射后端自动选择与动态高斯门控：阶段报告

## 1. 目标

本阶段不再扩大 UNSAFE 实验。UNSAFE 只用于确认新路径没有明显正确性或性能
退化；主要目标是 SAFE 证明：

1. 在进入 PDR 前判断电路是否值得使用 CMSat/高斯；
2. 已经进入 CMSat 后，判断继续维护高斯矩阵是否仍然划算；
3. 保留 `affine_phase_sync` 等高斯独有覆盖，同时避免 CRC residue 一类深层
   退化。

最终状态机是：

```text
静态结构分析
  |- 非高覆盖/非满秩仿射区域 -> CaDiCaL
  `- 全局或 guarded 仿射区域 -> CMSat + Gaussian
                                   |
                                   `- 在线低收益/超大矩阵 -> CMSat XOR-only
```

动态关闭是单向的。它不会重建求解器，不会丢掉已学习的 CDCL 子句，也不会
删除 XOR 约束；只删除高斯矩阵，随后仍由 CMSat 的原生 XOR watch 维护约束。

## 2. 新增的底层观测量

CryptoMiniSat 原来只公开总 conflicts/decisions/propagations。本阶段从每个
`EGaussian` 矩阵导出：

- `checks`：高斯检查/消元被调用的次数；
- `row_xors`：实际执行的矩阵行异或次数；
- `propagations`：高斯产生的单位传播；
- `conflicts`：高斯直接发现的冲突；
- `matrices/rows/columns`：矩阵数量与几何规模。

MC 在每次新建 frame 前汇总最近窗口，输出 `CMSAT_GAUSS_WINDOW`。第一版门控
满足以下任一条件并连续达到 patience 后关闭：

1. `(propagations + conflicts) / checks` 低于阈值；
2. 平均单矩阵面积超过预算。

默认值故意保守：frame 4 前不关闭，至少观察 10,000 次检查；低收益阈值为
0.1%，平均单矩阵上限为 1,000,000 cells。所有阈值均可通过环境变量复现实验。

## 3. 为什么只看“高斯推导很多”仍然会误判

两个代表模型揭示了关键差异：

- 有利 `affine_phase_sync`：窗口有效率约 42%，平均矩阵约
  `100 x 150`；
- 退化 CRC residue：窗口有效率仍约 48%，但平均矩阵约
  `1600 x 1800`。

所以“高斯产生了多少传播”不是充分条件。大矩阵上的一次传播可能需要大量
packed-word 行操作，其成本远高于 CDCL 的普通 BCP。矩阵几何规模是此前缺失的
第二维，这也解释了为什么旧的固定深度门控不稳定。

## 4. 初步联合实验

实验均为单线程 MC、同一固定 seed。比较五种配置：CaDiCaL、CMSat XOR-only、
Gaussian 常开、Gaussian 动态停止、静态选择加动态停止。

### 4.1 CRC residue 负对照（18 个，30 秒）

| 配置 | 解出 | 已解累计时间 | PAR-1@30s |
| --- | ---: | ---: | ---: |
| CaDiCaL | 17/18 | 31.18 s | 61.18 s |
| CMSat XOR-only | 12/18 | 51.97 s | 231.97 s |
| Gaussian 常开 | 6/18 | 6.60 s | 366.60 s |
| Gaussian 动态停止 | 12/18 | 78.92 s | 258.92 s |
| 两级自动策略 | 17/18 | 31.17 s | 61.17 s |

在线停止把常开高斯从 6 个恢复到 12 个，证明切换确实能终止部分矩阵退化；但
它仍不如 CaDiCaL。两级策略把 18 个模型全部静态拒绝给 CaDiCaL，因此结果与
CaDiCaL 基线几乎重合。这里的正确行为是“不进入”，动态停止只是保险。

### 4.2 Phase-sync 正对照（3 个，60 秒）

| 配置 | 解出 | PAR-1@60s |
| --- | ---: | ---: |
| CaDiCaL | 1/3 | 133.03 s |
| CMSat XOR-only | 2/3 | 86.56 s |
| Gaussian 常开 | 3/3 | 23.08 s |
| Gaussian 动态停止 | 3/3 | 23.06 s |
| 两级自动策略 | 3/3 | 11.04 s |

动态门控在三个模型上均未误关。两级策略识别出 guarded affine summary，并在
width 20 上得到最清楚的分离：CaDiCaL 与 XOR-only 均 60 秒超时，普通高斯
15.53 秒，自动 summary 加高斯 2.51 秒。

这些是机制和回归实验，不替代已有 1,800 秒、双 seed、rIC3 timeout 的 11 个
稳定 phase-sync 覆盖结果。当前新增结论是：自动选择可以保留该正域，同时在
CRC 负域回到 CaDiCaL。

## 5. 当前边界与下一步

1. 门控只在 frame 边界检查。如果求解器卡在第一个昂贵 predecessor 查询里，
   在线门控来不及触发；必须依靠静态选择，或以后增加按 SAT-call/时间窗口检查。
2. 当前矩阵成本使用面积代理，还没有直接记录 Gaussian CPU time。下一版可用
   低频采样计时，避免给每次矩阵操作加入昂贵时钟调用。
3. 需要在完整 SAFE 应用族上冻结阈值：正域至少覆盖 phase-sync、frame-align、
   frame-lock、scrambler/LFSR/syndrome；负域保留 residue 和 carry-dominated
   电路。阈值只能在训练子集调整，随后在独立尺寸与拓扑上验证。
4. 最终评价以额外覆盖和 PAR 为主，不以“门控触发次数”作为成功标准。门控不
   触发但正确保留 Gaussian，同样是正确决策。

## 6. 复现入口

- 二进制：`Modelchecker-bidirectional/modelchecker/modelchecker-gauss-auto-v1`
- 联合 runner：`test_tools/compare/pathb/run_affine_dynamic_gate.py`
- CRC 原始表：`results/pathb_affine_dynamic_gate_crc_v1`
- phase-sync 原始表：`results/pathb_affine_dynamic_gate_sync_v1.tsv`
- 环境开关：`MC_PDR_CMSAT_GAUSS_AUTO_GATE=1`

