# Private XOR-Island 压缩成果报告

## 1. 成果定位

本成果面向 CRC、LFSR、scrambler 等仿射数据通路。输入仍是普通 AIGER，MC
先恢复其中的 XOR 门，再把只在局部使用的二元 XOR 树压缩成一条宽 parity
equation，交给 CryptoMiniSat 的 Gaussian 模块。

目标不是证明 Gaussian 普遍优于 CDCL，也不是优化包含大量非线性逻辑的任意
电路，而是解决一个明确问题：

> 综合后的仿射网络被拆成大量二输入 XOR 门时，怎样避免 Gaussian 矩阵为
> 局部辅助变量反复维护等价的中间方程？

## 2. 为什么逐门 XOR 会浪费工作

假设电路计算：

```text
t1 = a XOR b
t2 = t1 XOR c
y  = t2 XOR d
```

逐门编码会向矩阵加入三条方程，并保留 `t1`、`t2` 两个只服务于这棵树的辅助
变量。Gaussian 消元需要维护三行之间的关系。对树外部而言，真正有意义的只有：

```text
y XOR a XOR b XOR c XOR d = 0
```

如果 `t1` 和 `t2` 没有被树外逻辑使用，就可以直接用后一条方程替换前三条。
这相当于在进入 SAT 求解前消去局部辅助变量，而不是改变电路功能。

## 3. Private XOR island 的定义

算法从外部可见的 XOR 输出向输入方向展开：

1. 当前节点是 XOR，且其输出只被岛内父节点使用时，继续展开；
2. 遇到输入、latch、AND/OR 或共享 XOR 输出时停止；
3. 停止位置成为 island boundary；
4. 用 GF(2) 对称差合并变量，重复出现两次的变量相互抵消；
5. 反相边被累计到方程右侧常数项。

最终得到：

```text
root XOR boundary_1 XOR ... XOR boundary_n = parity
```

“private”是替换正确性的关键。只要某个中间 XOR 输出还有外部 fanout，它就不
会被删除，而会成为 boundary。算法不根据 benchmark 名称选择结构。

## 4. 两种工作模式

### 4.1 Redundant summary

保留全部二输入 XOR 方程，同时额外加入宽方程。这种方式语义直接等价，但矩阵
可能同时维护原方程和摘要，通常只适合机制对照。

```text
MC_PDR_AFFINE_ISLAND_SUMMARY=1
```

### 4.2 Replacement

对满足 private 条件的岛删除内部逐门方程，仅加入宽方程。这是当前正结果使用
的模式：

```text
MC_PDR_AFFINE_ISLAND_REPLACE=1
MC_PDR_AFFINE_ISLAND_MIN_XORS=4
MC_PDR_AFFINE_ISLAND_MAX_SUPPORT=512
```

`REPLACE=1` 会隐式启用 summary。`MIN_XORS` 避免为很小的 XOR 树引入宽方程，
`MAX_SUPPORT` 防止单条方程过宽。

## 5. 正确性保护

确认实验可启用：

```text
MC_PDR_AFFINE_ISLAND_VALIDATE=1
```

验证器重新编码原始 gate network，并为每条摘要构造 mismatch 变量。它询问是否
存在一个赋值，使任意摘要与原网络不一致：

- 查询为 UNSAT：所有摘要通过，允许替换；
- 查询为 SAT：关闭全部 island summary/replacement，回退逐门编码。

验证使用的临时 gate/clause 不计入正式求解统计，耗时单独记录为
`island_validation_seconds`。

## 6. 公开数据结果

### 6.1 正确性回归

公开 CRC、LFSR 和 scrambler RTL 共 12 个 target。原始 CMSat、replace-min2、
replace-min4 三种配置均为 **12/12 SAFE**，没有结果分歧。

### 6.2 CRC32C 五种子结果

公开 Verilog 风格 `CRC32C w32/d16` 的固定 seed 结果：

| 配置 | 五次时间（秒） | 中位数 | 几何均值 |
| --- | --- | ---: | ---: |
| CMSat 逐门 XOR | 4.016, 3.514, 3.028, 4.020, 4.012 | 4.012 | 3.695 |
| replace-min2 | 1.018, 0.514, 0.520, 0.511, 1.009 | 0.520 | 0.675 |
| replace-min4 | 0.521, 0.518, 0.515, 0.513, 0.505 | 0.515 | 0.514 |

replace-min4 相对逐门 XOR 的中位时间降低 **87.2%**，约 **7.8x**。该 target
的既有 CaDiCaL 时间为 18.52 秒，所以在这个明确的仿射结构上，压缩后的
CMSat 同时优于未压缩 CMSat 和纯 CDCL。

这个 target 仍然较容易，因此结果证明的是机制有效和跨 seed 稳定，不代表新增
HWMCC 难题覆盖。

## 7. 可以与不能声称的内容

可以声称：

1. 能从 AIG/XAG 自动恢复 maximal private XOR islands；
2. 能在保持外部语义的条件下消去岛内辅助 XOR 变量；
3. SAT mismatch 验证与完整方向回归形成了正确性保护；
4. 公开 CRC32C 上获得跨 5 seed 的 7.8x CMSat 加速；
5. 适用范围是 XOR 密集、局部结果主要由仿射关系决定的数据通路。

不能声称：

- 对任意 HWMCC 模型都有收益；
- 已经比 rIC3 多解真实难题；
- 加法器、乘法器或其他 carry/AND 主导结构适合 Gaussian；
- 只要识别出 XOR，替换就必然改善 PDR 总时间。

## 8. 复现方法

构建和完整回归：

```bash
cd Modelchecker-bidirectional/modelchecker
make -j8
bash tests/run_directional_regression.sh
```

单模型运行：

```bash
MC_PDR_SOLVER=cmsat \
MC_PDR_CMSAT_GAUSS=1 \
MC_PDR_AFFINE_ISLAND_REPLACE=1 \
MC_PDR_AFFINE_ISLAND_MIN_XORS=4 \
MC_PDR_AFFINE_ISLAND_VALIDATE=1 \
MC_PDR_STATS=1 \
./modelchecker -xag MODEL.aag
```

实现与证据入口：

- `Modelchecker-bidirectional/modelchecker/PDR.cpp`
- `Modelchecker-bidirectional/modelchecker/tests/fixtures/unsafe_xor_chain_two.aag`
- `results/xor_island_compression_v1/public_affine_island_regression.tsv`
- `results/xor_island_compression_v1/public_crc32c_island_5seed.tsv`

两张结果表的 SHA-256 分别为
`4655abb1a957eb995efea6d74877662be1811c53326d7bdcb05b2c02f6359ba8` 和
`df18c44c312472fc72e3212a27beca4cd957ff6889f5498cb10458b9eb34c45a`。
