# 仿射数据通路 UNSAFE 构造与首轮实验

## 1. 实验问题

此前冻结的 375 个仿射数据通路模型全部为 SAFE，因此已有结果主要证明
Gaussian 有助于构造归纳不变式，不能回答它是否有助于寻找反例。本实验增加
结构配对、反例深度可控的 UNSAFE 模型，并分离以下因素：

1. CaDiCaL 与 CryptoMiniSat 后端差异；
2. 原生 XOR 与 Gaussian elimination 的差异；
3. 仿射 summary 的差异；
4. 始终维护 Gaussian 与在 frame 4/16 关闭矩阵的差异；
5. MC 单 lane 与 stock rIC3 四副本的差异。

## 2. 构造方法

语料库包含 48 个模型：

| 家族 | 结构点 | 反例深度 | 数量 |
| --- | --- | --- | ---: |
| CRC frame-align | CRC-16/32，64/256/1024 bit 每周期 | 2/8/32/128 | 24 |
| 64b/66b scrambler equivalence | 64/256/1024 bit 每周期 | 2/8/32/128 | 12 |
| streaming syndrome equivalence | 16/32/64 check bits | 2/8/32/128 | 12 |

每个模型从已有 SAFE 双实现模型开始，只在右侧实现的一个 latch next-state 上
加入一次性 XOR fault。一个确定性 one-hot phase chain 在标注深度的前一条
transition 激活 fault，因此 bad 在指定状态深度第一次成立。主体数据通路、
原始 property 和输入保持不变。

CRC witness 在第一个周期设置 SOF 完成双实现对齐；其余输入取零即可。全部 48
个模型经过重新生成 hash 检查和门级顺序模拟，观测到的首个 bad 深度与
2/8/32/128 标签完全一致。

该构造适合测量 UNSAFE 下的后端开销和深度敏感性，但 fault 无需满足复杂
parity signature，因此它还不是“Gaussian 困难反例”基准。

## 3. 30 秒完整拆分结果

MC 配置均为单 lane；rIC3 使用四个独立 IC3 副本。48 个模型使用同一 seed。

| 配置 | 解出 UNSAFE |
| --- | ---: |
| MC-XAG CaDiCaL | 42/48 |
| CMSat native XOR，无 summary，无 Gaussian | **48/48** |
| CMSat native XOR，无 summary，Gaussian | 47/48 |
| 自动 affine summary，无 Gaussian | **48/48** |
| 自动 affine summary，Gaussian | **48/48** |
| 自动 summary，frame 4 关闭 Gaussian | **48/48** |
| 自动 summary，frame 16 关闭 Gaussian | **48/48** |
| stock rIC3-4 | 22/48 |

CaDiCaL 的 6 个超时全部来自 witness depth 2 的 CRC frame-align；rIC3 在这
6 个点上也全部超时。CMSat native no-Gauss 和所有 summary 配置都在时限内
找到反例。

Gaussian 没有增加覆盖：

- native Gaussian 相对 native no-Gauss 新增 0，反而丢失 1 个 depth-128、
  1024-bit scrambler；
- summary Gaussian 相对 summary no-Gauss 新增 0；
- frame 4/16 门控与始终开启 Gaussian 的覆盖完全相同。

在 CaDiCaL 与候选共同解出的 42 个模型上，候选/CaDiCaL 墙钟几何均值比为：

| 配置 | 时间比，小于 1 才更快 |
| --- | ---: |
| native no-Gauss | 1.189 |
| native Gaussian | 1.676（共同解 41 个） |
| summary no-Gauss | 1.218 |
| summary Gaussian | 1.148 |
| frame-4 gate | 1.110 |
| frame-16 gate | 1.316 |

共同解统计排除了 CaDiCaL 超时的 6 个新增覆盖点，因此只能解释普通模型的
运行开销，不能代替带罚时的总体比较。

## 4. 当前结论

1. UNSAFE 上确实出现 MC 对 rIC3-4 的覆盖扩张：48 对 22；但这是构造域内
   结果，尚未经过 1,800 秒确认。
2. 这批新增覆盖不能归因于 Gaussian。CMSat native XOR 关闭 Gaussian 已经
   48/48，说明主要因素是 CMSat/XOR 呈现，而不是矩阵消元。
3. Gaussian 在大多数共同解上有额外成本；固定 frame 门控没有增加覆盖，
   frame 4 是当前共同解中成本最低的 Gaussian 配置，但仍慢于 CaDiCaL。
4. “浅层 CRC 比深层 CRC 更难”的反常现象再次出现。深层 one-hot phase chain
   给 CDCL 提供了强结构线索，因此本实验的 witness depth 不能简单解释为难度。

## 5. 下一步

下一组 UNSAFE 模型应让 fault 只在多个独立宽 parity 条件同时满足时激活，
并由预先构造的输入 witness 保证可达。这样 native no-Gauss 必须通过 CNF/CDCL
求解线性方程组，而 Gaussian 可以直接消元，才可能形成真正的
Gaussian-specific UNSAFE 区间。该组必须继续保留 CaDiCaL、CMSat no-Gauss、
CMSat Gaussian 和 rIC3-4 四个归因基线。

## 6. 产物

- 生成器：`pathb/families/unsafe_faults.py`
- 规格：`results/pathb_affine_unsafe_v1/specs.json`
- 冻结模型：`results/pathb_affine_unsafe_v1/benchmarks/manifest.json`
- 30 秒结果：`results/pathb_affine_unsafe_v1/screen_full_30s_seed1400003.tsv`
- 机器汇总：`results/pathb_affine_unsafe_v1/report_full_30s.md`
