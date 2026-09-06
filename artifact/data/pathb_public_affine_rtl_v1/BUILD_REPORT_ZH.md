# 公开仿射 RTL 到 AIGER 的构建与验证报告

## 1. 本次产物

本目录包含 12 个从公开 RTL 派生的时序 AIGER 安全模型，而不是仅由本项目
内部生成器构造的电路：

| 来源 | 模型 | 规模范围 |
| --- | --- | --- |
| OpenTitan `prim_lfsr` | 8、16、24、32、64、128 位 LFSR 转移监视器 | 35--395 latches，466--5506 ANDs |
| alexforencich `verilog-lfsr` | CRC-16/CCITT、CRC-16/IBM、CRC-32、CRC-32C、PRBS31、64b/66b scrambler | 32--116 latches，629--3228 ANDs |

AIG 文件位于 `aiger/`，完整参数、AIG 规模和每个文件的 SHA-256 位于
`manifest.json`。构建入口为：

```bash
python3 test_tools/compare/pathb/external_rtl/build_public_affine_aiger.py
```

## 2. 冻结的公开源码

| 项目 | commit | 使用文件 SHA-256 |
| --- | --- | --- |
| `lowRISC/opentitan` | `01a04ddc0759d0ce5425e5ee5dc2ddf804b23060` | `c61632878728613ba0403f2d068c03a5103165663b58d8dd50892ef032dec916` |
| `alexforencich/verilog-lfsr` | `c1f86d036745935f3812ec6ddc7821c70ef4c9de` | `5502c8203b0dfc7246c1a2de93e60c199ded3c1d7840b106350d714f72a9a079` |

综合工具为 Yosys 0.40。`verilog-lfsr/rtl/lfsr.v` 未被修改；wrapper 对同一
上游模块的 `LOOP` 与 `REDUCTION` 两种实现做逐周期等价验证。

OpenTitan 当前 RTL 使用了 Yosys 0.40 不支持的现代 SystemVerilog 多维参数和
数组初始化语法，因此构建脚本会先校验原文件 SHA-256，再生成
`derived_rtl/opentitan_prim_lfsr_yosys040.sv`。适配仅做三件事：

1. 展平未启用的 `StatePerm` 参数类型；
2. 移除本组模型不会读取的默认系数数组初始化，因为每个实例都显式设置
   `CustomCoeffs`；
3. 将明确关闭的 `NonLinearOut=0`、`StatePermEn=0` generate 分支专门化为
   上游定义的直通连接。

LFSR 的 Galois 转移、seed、entropy、enable 和 lockup recovery 逻辑均保留。
原文件、派生文件和 AIG 的哈希都写入清单，源码变化时脚本会拒绝静默适配。

## 3. 安全性质

- OpenTitan 模型使用独立参考方程监视每一步状态更新，包括 reset、外部 seed、
  enable、entropy 注入和全零锁死恢复。
- `verilog-lfsr` 模型从相同合法初态启动，证明 `LOOP` 与 `REDUCTION` 两种公开
  实现的当前状态、输出和下一状态始终一致。

这些性质具有真实 RTL 语义，但当前模型仍偏小，主要用途是公开来源的功能
回归、结构识别和自动后端选择测试；不能仅凭这组快速样例宣称高斯路线在公开
工业难题上取得速度优势。

## 4. 验证结果

修正 formal wrapper 初态后，使用
`modelchecker-gauss-auto-v1` 对每个模型运行以下 6 种单线程配置：CaDiCaL、
CMSat 无高斯、CMSat 高斯、动态门控、静态两阶段和静态加动态门控。

- 12/12 个模型均为 `SAFE`；
- 共 72 次运行，结果冲突数为 0；
- XAG 恢复识别出 30--923 个 XOR；
- 自动选择器在 7 个模型上选择 `cmsat-gauss-guarded-summary`，其余 5 个回退；
- 正式冒烟数据见 `smoke_fixed_60s.tsv`。

这轮只用于正确性验证。虽然 CRC-16/IBM、CRC-32 和 CRC-32C 上高斯配置在该次
短运行中明显快于 CaDiCaL，但样本小、绝对时间短且只使用一个种子，不能作为
最终性能结论。

`rejected_uninitialized_wrapper_smoke_60s.tsv` 是初版 wrapper 未固定监视器初态
时产生的无效结果，仅保留用于说明问题来源，不应进入任何统计。

## 5. 下一步

公开 RTL 基础已经建立。下一阶段应从同一公开模块构造更深的协议性质，例如
跨多拍并行/串行 CRC 等价、带 frame-valid 的 scrambler/descrambler 回环，以及
更宽数据路径的连续参数扫描；再寻找 CaDiCaL 的超时边界并比较高斯门控，而
不是继续把内部生成器结果当作公开数据集证据。
