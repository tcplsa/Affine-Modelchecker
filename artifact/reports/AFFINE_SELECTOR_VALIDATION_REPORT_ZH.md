# Affine-PDR Selector 阈值敏感性与留出验证报告

## 1. 结论先行

现有默认 selector `support=32, coverage=0.75, controls=2` 通过了冻结留出验证：

- 训练集：CaDiCaL 116/256，默认 selector 219/256；
- 留出集：CaDiCaL 74/131，默认 selector 122/131；
- 留出集新增 48 个解，丢失 0 个解，净增 48；
- 共同可解模型的时间几何均值比为 0.677，bootstrap 95% CI 为
  `[0.497, 0.888]`；
- 真正在线执行与离线重放在 387/387 个模型上的路径选择完全一致，留出集
  131/131 个最终状态一致。

这项实验支持的不是“32、0.75、2 是数学最优常数”，而是以下三个更稳健的
结论：support 在 16--64 内存在稳定平台；coverage 必须排除低覆盖、深层查询；
两个 control 足以覆盖当前常见的分段仿射结构。

## 2. 实验协议

语料共 387 个模型、16 个家族。实验前按完整结构组、拓扑、多项式和连续规模
区间冻结划分：

| 划分 | 数量 | 用途 |
| --- | ---: | --- |
| 训练集 | 256 | 选择阈值，不用于最终泛化结论 |
| 结构/规模留出 | 119 | 检查未见组合和较大连续规模 |
| 外部公开 RTL 留出 | 12 | 检查小型真实实现上的退化 |

每个模型只需运行六条底层路径：CaDiCaL、CaDiCaL affine hints、global
Gaussian，以及 control cap 为 1、2、3 的 guarded Gaussian。随后离线重放：

- support：16、32、64；
- guarded affine coverage：0.50、0.75、1.00；
- control cap：1、2、3。

共形成 27 个 selector。因为这些 selector 共享同一批路径运行，阈值差异不会
额外混入一次 SAT 随机性。所有路径固定同一 binary、seed、120 秒时限和
单线程 PDR policy。

## 3. 默认规则的留出结果

| 策略 | 留出求解数 | 新解 | 丢解 | 净增 | 几何均值比 |
| --- | ---: | ---: | ---: | ---: | ---: |
| CaDiCaL | 74/131 | -- | -- | -- | 1.000 |
| 默认 `32/0.75/2` | **122/131** | **48** | **0** | **+48** | **0.677** |

新增覆盖集中在适用域内，而不是来自随机散点：

| 家族 | 默认相对 CaDiCaL 新增覆盖 |
| --- | ---: |
| crc_frame_align | +24 |
| crc_frame_lock | +15 |
| scrambler_equiv | +3 |
| syndrome_equiv | +3 |
| affine_phase_sync | +2 |
| keccak_linear_equiv | +1 |

`crc_frame_residue` 上两者均为 12/12，说明默认 selector 在已知深层负域正确
回退，没有重复 Gaussian 常开的退化。

## 4. 三类阈值分别说明什么

### 4.1 Support 上限不敏感

固定 coverage=0.75、controls=2 时：

| support | 留出求解数 | 几何均值比 |
| ---: | ---: | ---: |
| 16 | 122/131 | 0.677 |
| 32 | 122/131 | 0.677 |
| 64 | 122/131 | 0.686 |

因此不能宣称 32 是精确最优值。更合理的解释是：16--64 都位于稳定平台，
support 上限主要防止非常宽的方程进入矩阵，而不是决定大多数模型是否启用
Gaussian。

### 4.2 Coverage 是关键边界

固定 support=32、controls=2 时：

| coverage | 留出求解数 | 新解/丢解 |
| ---: | ---: | ---: |
| 0.50 | 115/131 | 48/7 |
| 0.75 | **122/131** | **48/0** |
| 1.00 | 107/131 | 33/0 |

0.50 太宽松，会接纳深层 CRC residue，Gaussian 矩阵维护成本反而占主导；
1.00 太严格，会拒绝能由 guarded summary 处理的部分仿射模型。0.75 的意义是
要求大多数性质相关 next-state 已被少量 mode 覆盖，同时允许少数非仿射边界。

### 4.3 两个 Control 已足够

固定 support=32、coverage=0.75 时，control cap 1/2/3 分别解出 83/122/122 个
留出模型。一个 control 无法表达常见的分段 mode；增加到三个没有增加覆盖，
且 PAR-2 略差于两个。因此 cap=2 是当前语料上最小且充分的复杂度预算。

## 5. 一个重要的反过拟合结果

若完全按训练 solved count 和 PAR-2 选参数，会选择 `16/0.50/2`：训练集解出
225/256，比默认规则的 219/256 更多。但它在留出集只解出 115/131，并丢失
7 个 CaDiCaL 可解模型，几何均值置信区间也跨过 1。

这说明直接采用训练最优反而会破坏泛化。默认 `32/0.75/2` 是实验前已有规则，
留出结果只用于验证而没有再调参；它在留出集上零丢解，因此更适合作为论文和
实现中的保守默认值。

## 6. 在线实现校验

为了确认离线重放没有误解真实代码，我们又在同一 manifest 上运行了真实在线
selector：

- 路径选择一致：387/387；
- 留出集状态一致：131/131；
- 全部状态一致：382/387。

其余 5 个差异都位于训练集，且方向均为离线路径运行 TIMEOUT、在线重复运行
SAFE，发生在 120 秒边界附近。这属于重复运行波动，不是在线 selector 选择了
错误路径，也不影响留出覆盖结论。

## 7. 外部有效性边界

12 个公开 RTL 模型全部由 CaDiCaL 和 selector 解出。selector/CaDiCaL 时间
几何均值比为 0.685，但中位比为 1.000；整体收益由较重的 CRC-16/CRC-32 模型
驱动，而不是每个小模型都加速。

所以目前可以写：selector 在跨结构、跨规模的受控留出集上稳定扩展覆盖，并在
小型公开 RTL 上未造成退化。还不能写：它已经在困难工业 RTL 上获得广泛验证。

## 8. 复现文件

- 冻结 manifest：`results/pathb_affine_selector_validation_v1/manifest.json`
- 六路径原始结果：`results/pathb_affine_selector_validation_v1/oracle_120s.tsv`
- 在线 selector 结果：`results/pathb_affine_selector_validation_v1/online_default_120s.tsv`
- 完整 27 策略表：`results/pathb_affine_selector_validation_v1/report.md`
- 机器可读摘要：`results/pathb_affine_selector_validation_v1/summary.json`
- 一键入口：`run_affine_selector_validation.sh`

