# 结构选择型仿射 PDR：现版本详细技术路线

## 0. 阅读前先建立直觉

这一节假设读者熟悉普通软件和基本布尔逻辑，但没有系统学习过硬件模型检查。
第一次阅读时，可以先读本节、第三节、七节和十二节，再回头看公式。

### 0.1 我们验证的对象是什么

同步数字电路可以看成一个每次时钟沿执行一次的程序。软件程序可能写成：

```text
state = initial_state
while true:
    input = environment()
    state = next(state, input)
    assert(not bad(state))
```

硬件中的几个常用词可以直接对应到软件概念：

| 硬件/模型检查术语 | 软件直觉 |
| --- | --- |
| latch/register | 跨循环迭代保存的状态变量 |
| primary input | 每轮由环境传入的参数 |
| combinational logic | 本轮执行的纯函数 |
| next-state function | `next(state, input)` |
| bad property | 不允许触发的断言失败条件 |
| clock cycle | 循环执行一轮 |

例如一个两位寄存器：

```text
state = (s0, s1)
input = x
s0_next = s1 XOR x
s1_next = s0 XOR s1
bad = s0 AND s1
```

在一个时钟沿到来时，`s0_next` 和 `s1_next` 同时写回寄存器。验证任务是：
从初始状态出发，无论每轮输入 `x` 是什么，是否永远不会到达 `bad=1` 的状态。

### 0.2 为什么不能直接把所有状态走一遍

如果电路有 `n` 个 latch，就最多有 `2^n` 个状态。100 个 latch 已经对应
`2^100` 个状态，无法逐点枚举。模型检查器实际保存的是状态集合的逻辑描述，
并用 SAT 求解器回答类似问题：

```text
是否存在一个状态 s 和输入 i，满足：
    s 属于当前考虑的状态集合
    AND transition(s, i, s')
    AND s' 是坏状态？
```

SAT 返回 `SAT`，表示找到了一个具体前驱；返回 `UNSAT`，表示不存在这样的
前驱。IC3/PDR 就是通过许多这样的局部查询，逐步构造“坏状态永远不可达”的
证明。

### 0.3 SAT 和 CNF 是什么

SAT 求解器接收布尔公式，判断是否存在一组变量赋值使公式为真。多数 SAT
求解器要求公式写成 CNF，也就是“若干子句的 AND”，每个子句是“若干文字的
OR”：

```text
(a OR NOT b) AND (b OR c) AND (NOT a OR NOT c)
```

一条硬件门也可以变成 CNF。比如 `z = a AND b` 可写成三条子句：

```text
(NOT z OR a)
(NOT z OR b)
(z OR NOT a OR NOT b)
```

这种转换在逻辑上没有损失，但“同一个函数如何拆成变量和子句”会强烈影响
SAT 搜索路径。就像同一个程序换一种数据布局，算法结果不变，但缓存行为和
运行时间可能完全不同。

### 0.4 AIG、XAG 和 CNF 分别处在哪一层

可以把三者理解成编译流程中的不同中间表示：

```text
RTL/Verilog
    -> 逻辑综合
AIG 或 XAG 图
    -> SAT 编码
CNF / XOR-CNF
    -> 求解
SAT solver
```

- **AIG** 只使用 AND 节点和反相边，结构统一，适合逻辑综合和交换格式；
- **XAG** 额外允许显式 XOR 节点，更容易保留奇偶校验、CRC 等线性结构；
- **CNF** 是 CaDiCaL、MiniSat 等 CDCL 求解器通常看到的子句集合；
- **XOR-CNF** 同时包含普通 CNF 子句和 `x XOR y XOR z = b` 这样的原生
  方程，CryptoMiniSat 可以直接处理。

输入文件是 AIG 并不说明原电路没有 XOR。它只说明 XOR 已经在综合时被拆成
AND 网络。我们的第一步是从这些 AND 模板中重新识别 XOR。

### 0.5 XOR 为什么和普通 AND/OR 不太一样

XOR 表示“不同为 1”，也等价于模 2 加法：

```text
0 XOR 0 = 0
0 XOR 1 = 1
1 XOR 0 = 1
1 XOR 1 = 0
```

因此：

```text
x XOR x = 0
x XOR 0 = x
x XOR 1 = NOT x
```

一组只包含 XOR 的约束，就是 GF(2) 上的线性方程组。例如：

```text
x XOR y XOR z = 0
    y XOR z   = 1
```

将两行相消后立刻得到 `x=1`。这就是布尔版本的高斯消元。

普通 CDCL 并非不能解 XOR。任何 XOR 都能转换为 CNF；问题是，长 XOR 被
拆成许多局部门和辅助变量后，“两条长方程相消得到 x=1”这个全局关系被隐藏
了。CDCL 可能需要做很多决策和冲突学习，才能间接重建它。

### 0.6 高斯消元在这里做什么

这里的高斯消元不是处理浮点数，而是在 0/1 上做行消元：

```text
行 A: x XOR y XOR z = 0
行 B:     y XOR z   = 1
行 A XOR 行 B: x    = 1
```

CryptoMiniSat 同时运行两套互相协作的推理：

1. CDCL 处理普通 CNF、控制逻辑和学习子句；
2. Gaussian 模块处理原生 XOR 方程之间的线性关系。

它的代价是维护矩阵。若方程很短、很少或电路主要是非线性的，矩阵成本可能
比收益更大，所以不能无条件开启。这也是本工作必须做结构选择的原因。

### 0.7 IC3/PDR 到底在做什么

可以把 PDR 想成一名不断总结“哪些状态不可能在第 k 步以内到达”的分析器。
它维护一系列 frame：

```text
F0, F1, F2, ...
```

- `F0` 精确描述初始状态；
- `F1` 是对一步内可达状态的过近似；
- `F2` 是对两步内可达状态的过近似；
- frame 中的 clause 排除已经证明不可达的状态区域。

一次典型过程是：

1. 检查当前 frame 是否可能一步走到坏状态；
2. 如果可能，SAT 返回一个具体状态 cube，称为 CTI 或 obligation；
3. 继续向前找这个 cube 的前驱；
4. 如果最终连到初始状态，得到真实反例，结论是 UNSAFE；
5. 如果某处找不到前驱，就学习一条 clause，一次排除一整片状态；
6. 不断将学习到的 clause 向更高 frame 推送；
7. 当相邻两个 frame 相同，就得到归纳不变式，结论是 SAFE。

其中“cube”可以理解为一个具体或部分具体的状态条件：

```text
s0=1 AND s3=0 AND s7=1
```

“clause”通常是这个 cube 的否定，表示以后不需要再探索这一片状态。

### 0.8 为什么只改 transition 表示就会改变整个 PDR

PDR 的每一步都反复向 SAT 求解器提交包含 transition 的查询。即使逻辑完全
相同，两种表示也可能让 SAT 返回不同的满足赋值和不同的 UNSAT core：

```text
表示方式
   -> 单次 SAT 查询快慢
   -> 返回哪个 predecessor
   -> 学到哪条 lemma
   -> 后续产生哪些 obligation
   -> 整条 PDR 搜索轨迹
```

所以我们的处理既可能让“同一道 SAT 查询”变快，也可能使 PDR 从一开始就走
一条更容易收敛的证明路径。

### 0.9 一个贯穿全文的小例子

考虑带 enable 的两位线性状态机：

```text
if en == 0:
    s0' = s0
    s1' = s1
else:
    s0' = s1 XOR x
    s1' = s0 XOR s1
```

从整个公式看，`en ? value1 : value0` 是 mux，含 AND/OR，所以不能直接写成
一个全局线性矩阵。但固定 `en` 后：

```text
模式 en=0:
    s0' XOR s0 = 0
    s1' XOR s1 = 0

模式 en=1:
    s0' XOR s1 XOR x = 0
    s1' XOR s0 XOR s1 = 0
```

guarded-affine 分析正是在自动恢复这四条关系。编码时加入：

```text
en=0 -> 使用 hold 方程
en=1 -> 使用 update 方程
```

这样 mux 控制仍由 CNF/CDCL 处理，模式内部的宽 XOR 数据变换由 Gaussian
处理。这就是当前系统最核心的技术，而不是简单地把所有门交给 CMSat。

### 0.10 后文术语速查

| 术语 | 本文中的意思 |
| --- | --- |
| transition/T | 当前状态和输入如何决定下一状态 |
| primed latch `s'` | 下一时钟周期的状态变量 |
| support | 一条 XOR 方程中实际出现的变量集合 |
| affine | XOR 变量集合再加一个 0/1 常数 |
| rank | 方程组中相互独立的约束数量 |
| guard | enable/reset/mode 等模式条件 |
| summary | 跳过中间门，直接描述输入到下一状态的等价方程 |
| hint | 不删除原编码，额外加入的等价冗余约束 |
| backend | 真正执行 SAT 查询的求解器，如 CaDiCaL/CMSat |
| fallback | 结构条件不满足时保留普通求解路径 |
| SAFE | 存在证明，坏状态不可达 |
| UNSAFE | 存在从初始状态到坏状态的反例路径 |

## 1. 研究问题与当前定位

现版本要解决的问题不是“凡是包含 XOR 的电路都换成
CryptoMiniSat”，也不是“构造一批只适合高斯消元的人工 SAT 题”。真正
的问题是：

> 当硬件下一状态逻辑本身包含大规模线性或分模式线性的数据变换时，能否
> 从普通 AIGER 输入中恢复这种语义，并在不改变 PDR 正确性与硬件设计的
> 前提下，自动选择更合适的 SAT 表示和求解后端？

当前答案是一条结构选择型路线：

1. 从 AIGER 中恢复 XOR/XAG 结构；
2. 将每个 latch 的下一状态函数符号化为 GF(2) 上的仿射方程；
3. 如果控制逻辑破坏了全局仿射性，则固定少量 enable/reset/mode 信号，恢复
   分模式仿射方程；
4. 根据仿射覆盖率、矩阵秩、平均 support 和控制模式复杂度，在 CaDiCaL
   与 CryptoMiniSat 之间自动选择；
5. PDR 的 obligation、blocking、MIC/CTG、push 和不动点判断保持不变。

因此，现版本的主要贡献单位不是“一个新 SAT 求解器”，而是：

```text
硬件转移结构恢复
    +
结构驱动的 SAT 表示选择
    +
在增量 PDR 查询中的原生仿射推理
```

## 2. 适用范围

### 2.1 当前目标结构

当前主要适用于以下时序数据通路：

- CRC 帧对齐器和帧锁定器；
- 线性 scrambler/descrambler；
- syndrome、奇偶校验和线性编码更新逻辑；
- 仿射状态变换和部分 LFSR jump/equivalence；
- 含少量模式控制的大规模线性流水线。

这些电路在 RTL 中经常具有如下形式：

```text
if reset:
    state' = constant
elif enable:
    state' = A * state XOR B * input XOR c
else:
    state' = state
```

其中乘法和加法均在 GF(2) 上进行。综合成 AIG 后，矩阵 `A` 和 `B` 不再
显式存在，而是被拆成大量 AND、反相边和 XOR 模板。现版本试图从综合结果
中把这些关系重新恢复出来。

### 2.2 “XOR 多”不是充分条件

以下结构即使 XOR 数量较多，也不一定适用：

- XOR 只位于很小的局部组合锥中；
- 乘法、carry、S-box 等非线性部分主导 SAT 难度；
- 每个 latch 的更新由大量相互独立的 mode 控制；
- 仿射方程很短，普通 CDCL 的单位传播已经足够；
- 性质本身与仿射数据通路几乎无关。

所以选择器使用的是“下一状态仿射覆盖和耦合强度”，而不是简单的 XOR
门占比。

## 3. 从输入到 PDR 的完整数据流

```text
                      AIGER 模型
                          |
                          v
                等价的 AIG -> XAG 恢复
                          |
                          v
          +--------- 下一状态结构分析 ---------+
          |                    |                |
          v                    v                v
      全局仿射             分模式仿射        无可靠结构
          |                    |                |
     support/rank         control/coverage      |
          |                    |                |
      +---+---+                |                |
      |       |                |                |
    稀疏     稠密              |                |
      |       |                |                |
      v       v                v                v
 CaDiCaL   CMSat+Gauss   CMSat+guarded      普通门级
 +CNF提示   +原生摘要      affine summary     fallback
      |       |                |                |
      +-------+----------------+----------------+
                          |
                          v
       predecessor / block / MIC-CTG / push / fixed point
                          |
                          v
                SAFE invariant 或 UNSAFE witness
```

自动选择只读取当前模型的结构统计，不读取：

- 文件名和 benchmark family 名称；
- 已知 SAFE/UNSAFE 标签；
- 历史运行时间；
- rIC3 或其他求解器结果。

这保证最后的方法可以部署在未知模型上，而不是实验后的按题选配置。

## 4. 第一层：AIG 到 XAG 的等价恢复

AIGER 原始输入只显式提供 AND 和反相边。一个二输入 XOR 通常会被综合为
四个 AND 相关的子结构。MC 先识别这些模板，将其恢复为：

```text
z = x XOR y
```

恢复过程只改变内部表示，不改变布尔函数。其作用有两个：

1. 避免后面的仿射分析在 AND 网络中猜测 parity；
2. 让支持原生 XOR 的 SAT 后端直接接收方程，而不是重新 CNF 化。

这里需要强调：XAG 是语义恢复的入口，不是当前提升的完整解释。现有实验中
MC-XAG 在目标组只解出 70/216，而加入仿射摘要和后端选择后解出
208/216，说明“恢复单个 XOR 门”和“恢复完整下一状态方程”是两个不同
层次。

## 5. 第二层：全局仿射下一状态恢复

### 5.1 符号表达

对输入变量和当前状态变量建立单位向量式表达：

```text
E(x_j) = ({x_j}, 0)
```

表达 `(S,b)` 表示：

```text
XOR(S) XOR b
```

沿 XOR 门传播时：

```text
E(u XOR v) = (S_u symmetric_difference S_v, b_u XOR b_v)
```

同一变量出现两次会在 GF(2) 中抵消。反相边不改变 support，只翻转常数：

```text
E(NOT u) = (S_u, b_u XOR 1)
```

如果某个下一状态锥遇到无法化为常数或 XOR 的 AND/OR，则该 latch 不被
标记为全局仿射。

### 5.2 得到状态更新矩阵

对每个 latch `s_i`，恢复：

```text
s_i' = XOR(S_i) XOR b_i
```

将所有方程写成矩阵形式即：

```text
s' = A*s XOR B*i XOR c
```

实现同时统计：

- `affine_next_count`：成功恢复的 latch 数；
- `affine_support_sum/max`：方程 support 总量和最大值；
- `affine_next_rank`：恢复方程组的 GF(2) 行秩。

秩通过稀疏集合上的增量异或消元计算。当前全局自动路径采用较保守的门槛：

```text
affine_next_count == num_latches
affine_next_rank  == num_latches
```

也就是所有 latch 都必须可恢复，并且方程组具有满 latch 行秩。这样可以避免
只看到一个局部 XOR 锥，就把整个 PDR 实例错误地切换到高斯后端。

### 5.3 伪代码

```text
for each primary input or latch x:
    expr[x] = ({x}, 0)

for xor gate z = a XOR b in topological order:
    if expr[a] and expr[b] exist:
        expr[z].support = expr[a].support XOR expr[b].support
        expr[z].constant = expr[a].constant XOR expr[b].constant
                           XOR edge_sign(a) XOR edge_sign(b)

for each latch s_i:
    if expr[next_i] exists:
        record equation expr[next_i] XOR s_i' = 0
        insert its row into an incremental GF(2) basis
```

## 6. 第三层：受控制信号保护的仿射恢复

### 6.1 为什么需要 guarded affine

真实数据通路往往包含 mux：

```text
next = enable ? affine_update : hold
```

`enable AND affine_update` 从全局看是非线性的，因此仅做纯 XOR cone 分析会
失败；但在 `enable=0` 和 `enable=1` 两个模式内，下一状态仍然分别是仿射
函数。guarded affine 的目标是保留这种分段线性结构。

### 6.2 控制信号选择

当前实现不再把变量在 AND/OR 节点中的出现次数当作主要分数。出现次数高只
说明一个信号经常参与非线性门，并不说明固定它以后能恢复多少下一状态方程。
选择器现在分成三步：

1. 沿门的消费者方向计算每个候选能覆盖多少 `next` 根和性质根，先保留
   cone-dominant 候选；
2. 把候选加入当前 guard 集，快速估计“所有模式下都变成仿射”的 latch
   数量，按边际 coverage gain 贪心选择；
3. 对最终入选的 control 用精确 support 集重新计算全部方程，快速估计只
   参与选点，绝不参与最终编码。

单控制贪心还会漏掉嵌套 mux。例如 CRC frame-align 同时包含 `sof` 和
`valid`：只固定任意一个都几乎没有收益，同时固定两个才能恢复完整数据通路。
因此选择器还会在 occurrence 最高的 3 个候选中做一次受限二元 look-ahead，
只检查 3 对。它能发现控制协同，同时避免在宽数据通路上枚举大量候选组合。

快速估计使用两个确定性的 64 位 XOR 指纹表示 support。它保留 XOR 抵消和
常量判断，碰撞概率可以忽略；即便估计阶段发生碰撞，最终精确重算也会拒绝
没有真实增益的 control。出现次数现在只用于最后的平分决胜。

```text
guarded_affine_max_controls = 2  (默认)
```

最多枚举 `2^2=4` 个模式。代码允许的硬上限为 8，但不适合在当前算法下
直接提高，因为编码规模随模式数指数增长。

### 6.3 每个模式内的常量传播

固定 control assignment 后，对每个门递归求值：

- XOR：合并两个仿射表达；
- `0 AND x = 0`；
- `1 AND x = x`；
- `1 OR x = 1`；
- `0 OR x = x`；
- 如果 AND/OR 两边都仍是非恒定表达，则该节点在本模式下不可恢复。

只有某个 latch 在所有枚举模式下都恢复成功，才记录该 latch 的 guarded
方程集合：

```text
g_m -> (s_i' = XOR(S_i,m) XOR b_i,m)
```

当前自动选择要求：

```text
guarded_affine_next_count / num_latches >= 0.75
```

剩余未恢复 latch 仍使用原始门级编码，因此并不要求整个模型完全线性。

### 6.4 正确性校验接口

实现提供 `MC_PDR_GUARDED_AFFINE_VALIDATE=1`。校验器对每个模式构造：

```text
原始 transition cone
AND 当前 guard
AND (原始 next != 仿射 summary)
```

如果 SAT，说明摘要不等价并立即回退；所有模式均 UNSAT 才通过。该验证是
可选的离线确认模式：在 2,048-bit CRC 上，选择和精确重算约需 3.7 秒，但
对完整原始 cone 做 SAT 等价验证可能超过 30 秒，因此不应成为每次生产求解
的固定开销。当前代表性 320-bit CRC 和 phase-sync 模型均已通过验证；正式
论文应对分层代表点保存验证结果，而常规批量运行使用已验证的恢复算法。

## 7. 第四层：三条 SAT 呈现路径

### 7.1 路径 A：稀疏全局仿射 -> CaDiCaL + parity hints

选择条件：

```text
全 latch 仿射
AND 满秩
AND average_support <= 32
```

该路径保留 CaDiCaL 和原始门级 CNF，同时把每个长方程编码为一个顺序 XOR
辅助链。例如：

```text
s' = a XOR b XOR c
```

增加：

```text
t = a XOR b
s' = t XOR c
```

每个二输入 XOR 用四个 CNF 子句编码。这组 clauses 与原 transition 是等价
冗余信息，因此称为 hint：它不删掉原逻辑，只给 CDCL 一条更直接的长程
parity 传播路径。

为什么稀疏时保留 CaDiCaL：

- 方程短时高斯矩阵维护成本可能大于收益；
- CaDiCaL 的传播、重启和 clause learning 对普通 CNF 更成熟；
- 冗余 parity 链已经能降低综合网络带来的中间变量距离。

### 7.2 路径 B：稠密全局仿射 -> CMSat + native XOR + Gaussian

选择条件：

```text
全 latch 仿射
AND 满秩
AND average_support > 32
```

该路径将 PDR 的 active SAT backend 切换为 CryptoMiniSat，并开启：

```text
MC_PDR_CMSAT_GAUSS=1
MC_PDR_CMSAT_SIMPLIFY=0
```

对已经恢复的 latch，不再通过整个原始 next-state XOR 树表达其更新，而是
直接加入：

```text
XOR(S_i, s_i') = b_i
```

这与 CaDiCaL hints 有本质区别：

- CaDiCaL 路径：原门级 CNF仍在，摘要是冗余增强；
- CMSat 路径：摘要替代该 latch 的原 next-cone 绑定，原生 XOR 直接成为
  transition relation 的呈现方式。

性质锥、约束锥和未摘要部分仍按需要编码。Gaussian 模块可以联合多条
next-state 方程，在 GF(2) 上产生单位关系或矛盾，而不必等待 CDCL 通过一串
CNF conflict 间接学习同样的 parity 后果。

### 7.3 路径 C：分模式仿射 -> guarded summary + Gaussian

如果全局路径失败，但 guarded coverage 达到 75%，选择：

```text
CMSat + native XOR + Gaussian + guarded affine summaries
```

对模式 `m` 和 latch `i` 新建 summary variable `q_i,m`：

```text
XOR(S_i,m, q_i,m) = b_i,m
```

再加入两个 guarded implication clauses：

```text
NOT guard_m OR NOT s_i' OR q_i,m
NOT guard_m OR     s_i' OR NOT q_i,m
```

当 guard 全部满足时，两条子句强制：

```text
s_i' <-> q_i,m
```

任意完整 control assignment 恰好激活一个模式，因此所有模式合起来精确
覆盖原始分段 transition。reset、enable、lock 状态等控制逻辑留在 CNF，
大规模数据变换留在原生 XOR 矩阵中。

这条路径是当前 frame-align、frame-lock 和 scrambler 等目标组提升的主要
来源：216 个目标模型中有 141 个选择了 guarded-summary。

### 7.4 路径 D：保守 fallback

如果以上条件均不满足：

```text
affine_auto_choice = fallback
```

系统继续使用用户请求的普通后端和门级 encoding。当前实验将默认后端设置
为 CaDiCaL，因此 auto selector 不会因为“检测到几个 XOR”就强制全模型进入
CMSat。

## 8. 与 PDR 循环的关系

仿射路线没有绕过 PDR。改变的是每个 SAT 实例看到的 transition relation
表示，PDR 外层仍执行：

1. `F_k AND T AND Bad'` 检查是否存在坏状态前驱；
2. 为 SAT predecessor 生成 proof obligation；
3. 递归阻塞 obligation；
4. 用 failed-assumption core、MIC 和 CTG 泛化 cube；
5. 将 lemma 放入相应 frame；
6. 尝试 push lemma；
7. 相邻 frame 相等时得到归纳不变式。

CMSat wrapper 实现了和原求解器一致的增量接口：

- `add` / native `add_xor_clause`；
- assumptions；
- SAT model；
- failed-assumption core；
- terminate callback；
- conflicts、decisions、propagations 统计。

因此高斯消元不是一次性的前处理，也不是先求一次结果再喂给 PDR；它存在于
translation、lift 等增量 solver 中，参与 PDR 反复生成的 SAT 查询。

## 9. 为什么可能加速

### 9.1 缩短语义距离

AIG/CNF 中，一个宽 parity 关系可能经过几十至几百个中间变量。CDCL 需要
多次 decision、propagation 和 conflict 才能重建端到端关系。仿射摘要把：

```text
输入/当前状态 -> XOR树 -> 中间节点 -> primed latch
```

压缩为：

```text
输入/当前状态 <-> primed latch 的一条 GF(2) 方程
```

### 9.2 跨方程联合推理

关键收益不只来自单条 XOR。设：

```text
x XOR y XOR z = 0
y XOR z         = 1
```

高斯消元立即推出 `x=1`。CNF-CDCL 也能最终证明，但通常需要选择变量并产生
冲突。状态更新矩阵越稠密、方程之间重叠越多，这种联合推理价值越大。

### 9.3 改变 PDR 轨迹

更便宜或更强的 SAT 推理还会间接改变：

- 返回的 predecessor model；
- UNSAT assumption core；
- MIC 删除 literal 的顺序结果；
- lemma 大小与后续 push 成功率；
- 最终访问的 obligation 路径。

所以最终加速包含两部分：同一查询内部 SAT 成本下降，以及 model/core 改变
后整个 PDR 查询流发生变化。当前结果证明了端到端收益，但尚未用
frozen-query replay 完全分解这两个分量。

## 10. 正确性边界

正确性依赖四层保障：

1. AIG->XAG 恢复必须保持布尔等价；
2. 全局摘要只穿过可证明为 XOR/常量的节点；
3. guarded 摘要只在对应 guard 下生效，未恢复部分保留原门级编码；
4. 最终 SAFE/UNSAFE 仍由完整 PDR + SAT 求解，并输出 invariant/witness。

需要区别“算法正确”和“选择器有效”：

- 选择错后端可能变慢，但不应改变结论；
- 摘要构造错误会影响 soundness，所以必须用等价验证和证书验证防守。

当前 375 模型短实验中 treatment/control 没有出现结论冲突，但这不能替代
正式的 summary equivalence validation。

## 11. 当前实现参数与决策树

实验配置：

```text
MC_PDR_SOLVER=cadical
MC_PDR_CMSAT_GAUSS=1
MC_PDR_CMSAT_SIMPLIFY=0
MC_PDR_AFFINE_AUTO=1
MC_PDR_GUARDED_AFFINE_AUTO=1
```

默认阈值：

```text
global coverage       = 100%
global rank           = num_latches
CaDiCaL support bound = 32
guarded coverage      = 75%
guard control count   = 2
```

实际决策等价于：

```text
if all_latches_affine and full_rank:
    if average_support <= 32:
        choose cadical-hints
    else:
        choose cmsat-gauss-summary
elif guarded_affine_coverage >= 0.75:
    choose cmsat-gauss-guarded-summary
else:
    choose fallback
```

程序输出 `auto_choice`、coverage、rank、support、guarded mode 数和编码方程数，
因此每个模型为何走某条路径是可解释、可复查的。

## 12. 当前实验结果如何支持路线

去重后的完整设计范围共 375 个模型：

| 范围 | 模型数 | MC-XAG 单线程 | MC-affine 单线程 | stock rIC3-4 |
| --- | ---: | ---: | ---: | ---: |
| 目标仿射数据通路 | 216 | 70 | **208** | 73 |
| 边界/非目标结构 | 159 | 107 | **122** | 97 |
| 总计 | 375 | 177 | **330** | 170 |

目标组的含义最重要：

- 相对 MC-XAG 新增 138 个解，未丢失已解模型；
- 严格排除 rIC3 异常退出后，有 114 个模型是 MC-affine 解出而 rIC3-4
  真正达到 120 秒超时；
- 共同解出的 72 个目标模型上，MC-affine/rIC3-4 几何时间比为 0.303；
- MC-affine 使用一个 solver lane，rIC3-4 使用四个独立 IC3 副本。

按目标家族看：

| 家族 | MC-XAG | MC-affine | rIC3-4 | MC 解出且 rIC3 真超时 |
| --- | ---: | ---: | ---: | ---: |
| CRC frame-align | 8/88 | **88/88** | 10/88 | 78 |
| CRC frame-lock | 7/41 | **38/41** | 12/41 | 27 |
| scrambler equivalence | 14/22 | **22/22** | 14/22 | 8 |
| syndrome equivalence | 14/22 | **22/22** | 21/22 | 1 |

LFSR 组中 stock rIC3 是 exit code 2，不属于真实 timeout，因此不能放入“突破
rIC3”的数字。这一排除规则已经写进分析器。

边界组相对 MC-XAG 为新增 16、丢失 1，说明 selector 已经明显降低了专用
后端的风险，但还没有达到“对任意硬件无损”的程度。论文应主张特定结构域
上的优势，而不是普适替换。

### 12.1 HWMCC 通用外溢探测

为了检查该机制在人工设计范围之外是否会偶然增加覆盖，另行启动了 HWMCC
全量四 lane CMSat+Gaussian 探测。任务在 `1,398/1,980` 个模型完成时停止，
因为严格交集已经给出清晰的否定信号：

- 已完成模型中有 331 个属于 stock rIC3-4 在 3,600 秒内未解的冻结难题集；
- 当前配置解出其中 3 个；
- 这 3 个全部已被历史 MC-AIG-4 解出；
- 相对已知 `MC-AIG union MC-XAG` 的新增覆盖为 **0**。

三个交集解中，两个 ZipCPU SAFE 模型走普通 fallback，另一个
`2024__gcd_2+newton_3_7` 是深度 1 的 UNSAFE，并走 guarded summary。因此
这批数据不支持“Gaussian 是通用 HWMCC 求解增强”的主张，也没有继续跑完
剩余 582 个模型的研究收益。它支持的决策是回到结构选择路线：只在可以静态
恢复高覆盖仿射 next cone 的目标域启用专用后端，其余模型回退。

## 13. 现版本尚未完成的部分

### 13.1 长时限确认

120 秒结果用于确定适用区间和缩放边界。最终“解决 rIC3 难题”的结论仍需：

- 对分层抽取的模型运行 1,800 秒；
- 重复独立进程启动；
- 验证 SAFE certificate 或 UNSAFE witness；
- 确认 rIC3 是 timeout 而不是 parser/backend error。

截至 2026-08-19 22:56，30 个分层确认模型中已经完成至少 25 个。前 24 个
已汇总结果覆盖 12 个 CRC frame-align、8 个 CRC frame-lock 和 4 个
scrambler-equivalence 模型：

- MC-affine 单线程对这 24 个模型全部证明 SAFE；
- stock rIC3 的四个独立 IC3 副本对这 24 个模型全部达到 1,800 秒时限；
- 已完成的 12 个 frame-align 结果中，MC 用时 0.52--6.54 秒，并跨越
  16/32/64 位 CRC 状态宽度和 32--1536 位 symbol 宽度。

这是已经跨三个家族出现的强烈长时限信号，但任务仍在运行，最终数字必须以
30 个模型全部写入结果文件后的汇总为准。

### 13.2 深层高斯退化

现版本在开始 PDR 前静态选择一个后端，并全程使用。随着 frame 加深：

- frame clauses 增多；
- 非仿射 lemma 逐渐占主导；
- 高斯矩阵维护成本可能继续增长；
- 原始仿射 transition 的边际贡献可能下降。

因此下一步要观测“每个时间窗口中的高斯 deduction/conflict/rank 收益”，而
不是仅按总电路结构决定全程开启。只有动态停止或切换后的端到端时间优于纯
CaDiCaL，深层回退才有意义。

第一版执行机制已经实现为单向门控：浅层使用 CMSat 的原生 XOR 和高斯矩阵；
达到指定 PDR frame 后，删除高斯矩阵，但保留 CMSat、已经学习的 CDCL 子句
以及普通 XOR 传播。这样没有重新编码和丢失学习结果的额外混杂，可以先独立
回答“停止维护矩阵本身是否有用”。环境变量
`MC_PDR_CMSAT_GAUSS_DISABLE_DEPTH=N` 用于机制实验，默认值 `-1` 表示不
门控。`PDR_AFFINE` telemetry 会记录门控深度、实际触发 frame 和被切换的
solver 数量。

这还不是最终的自适应策略。固定深度只提供可重复的消融轴；最终开关应该基于
滑动窗口中的收益/成本比，例如：

```text
gauss_value = (XOR 单位推导 + XOR 冲突 + 降秩量)
              / (矩阵行操作 + 高斯耗时)
```

当 `gauss_value` 连续多个窗口低于阈值，并且普通 frame clause 已经明显多于
原始仿射方程时，才关闭矩阵。为了避免来回切换造成抖动，第一版采用单向状态机：
`GAUSS_ACTIVE -> XOR_PROP_ONLY`，本次 PDR 运行不再重新开启。

机制冒烟实验已经确认切换可以安全执行：在一个需要 3--4 个 frame 的
`affine_phase_sync` 模型上，depth 2/3/4 三个切换点都最终得到 SAFE，且
telemetry 显示 7--8 个已经建立的 CMSat 实例完成了切换；三个 SAFE/UNSAFE
小型回归模型在门控开关前后结果也一致。不过该模型上固定 depth 2 的用时约
3.68 秒，始终开启高斯约 2.61 秒。因此当前证据只证明“切换机制正确可用”，
不证明“固定深度门控更快”；后续必须用求解器内部收益计数触发。

截至 2026-08-20，收益驱动版本已经实现。CryptoMiniSat 现在向 MC 导出高斯
检查、行异或、传播、冲突和矩阵规模；MC 在 frame 边界用近期收益率与平均矩阵
面积执行单向门控。初步正负对照表明：动态停止将 CRC residue 上常开高斯的
覆盖从 6/18 恢复到 12/18；更完整的“静态选择 + 动态停止”在该负域保持
CaDiCaL 的 17/18 覆盖，同时在 3 个 phase-sync 正对照上保持 3/3，并将其中
width-20 模型从普通高斯 15.53 秒降至 2.51 秒。详细数据和限制见
`AFFINE_DYNAMIC_GATE_REPORT_ZH.md`。

### 13.3 partial affine

当前全局路径要求 100% latch 覆盖，guarded 路径要求 75%。更一般的硬件可能
只有性质相关 cone 是仿射的。后续应按 PDR 查询实际涉及的 primed latch 和
bad cone 覆盖率选择，而不是按全模型 latch 比例选择。

这里的核心不是“删掉剩余电路”，而是只对值得的部分建立仿射摘要。假设一个
设计有 10,000 个 latch，但当前性质的 bad cone 最终只依赖其中 600 个；如果
这 600 个 next-state 函数中有 500 个可以写成 XOR 方程，那么全局覆盖率只有
5%，性质相关覆盖率却是 83%。按全局比例会错误放弃一个很有价值的区域。

选择过程分成静态和动态两层：

1. **静态性质相关性**：从 bad output 反向遍历组合逻辑和 latch 依赖，得到
   property cone；优先摘要其中的 affine next cone。
2. **动态查询热度**：统计 primed latch 在 predecessor assumptions、CTI、
   UNSAT core 和高频 lemma 中出现的次数。PDR 实际频繁询问的 cone 权重更高。
3. **预算选择**：在矩阵行数、总 support 和 guard mode 数预算内，贪心加入
   `热度 x 仿射覆盖收益 / 编码成本` 最大的 next cone。

正确性边界很重要：被选中的 latch 用等价 XOR 方程替代原 next cone；未选中的
latch 仍保留原始门级 CNF。partial summary 只改变等价约束的呈现方式，不是
抽象掉不相关状态，因此不需要靠实验结果保证正确性。

### 13.4 控制信号识别

出现次数只是第一版启发式。更好的分数应综合：

- 控制该信号后新增多少可恢复 latch；
- 对 bad/next cone 的支配范围；
- 是否接近 mux select、reset、enable；
- 增加一个 control 后模式数量与 affine coverage 的边际比值。

#### 13.4.1 为什么 occurrence score 不够

当前分数近似回答“这个输入在多少个 AND/OR 门里出现”。它很便宜，但高频不
等于有用：全局 reset 可能出现几千次，却只产生“全部清零”这一种平凡模式；
反过来，一个只出现几十次的 mode select 可能恰好把 500 个 latch 的非线性
mux 拆成两个完整的仿射数据通路。

#### 13.4.2 coverage-gain

对候选 control `c`，临时把 `c=0` 和 `c=1` 代入 next-state cone，再运行一次
仿射恢复。它的边际收益定义为：

```text
coverage_gain(c | C)
  = affine_latches(C union {c}) - affine_latches(C)
```

其中 `C` 是已经选中的 control 集合。分母需要惩罚新增模式数，因为每加一个
布尔 control，最坏会让模式数翻倍。实际选择的是近似
`coverage_gain / added_modes`，而不是单纯追求覆盖率。

#### 13.4.3 cone-dominance

cone-dominance 回答另一个问题：“这个信号控制的逻辑是否位于许多重要路径的
共同入口？” 从候选信号向前遍历，统计它能够支配或影响多少 next root，并对
bad cone、当前高频查询 cone 和普通无关 cone 分别赋高、中、低权重。一个真正
的 pipeline enable 或 mode select 往往在结构上位于大片 next cone 的上游；
偶然重复的数据位即使 occurrence 很高，也不会支配这些根。

第一版贪心分数可以写成：

```text
score(c | C) = w1 * newly_affine_property_latches
             + w2 * newly_affine_hot_latches
             + w3 * dominated_bad_cone_roots
             - w4 * added_modes
             - w5 * added_equation_literals
```

每轮加入分数最高且收益为正的 control，直到达到 mode/矩阵预算。这样选出的
guard 是“能让求解器多恢复一块有用线性数据通路的控制信号”，而不是“文件里
出现次数最多的变量”。

## 14. 下一阶段技术路线

建议按以下顺序推进：

1. **铆定证据**：完成 1,800 秒确认，冻结成功家族、宽度和控制复杂度边界；
2. **解释成功与失败**：按 coverage、rank、support、control、PDR depth 和
   Gaussian work 对模型分桶；
3. **改进 guard 选择**：从 occurrence score 升级为 coverage-gain 和
   cone-dominance；
4. **性质相关 partial summary**：只摘要当前 PDR 查询高频访问的 affine
   next cone；
5. **深层动态门控**：当单位推导/矩阵操作收益持续下降时停止高斯维护，或
   将已得到的短 parity consequences 注入 CaDiCaL；
6. **现实 RTL 验证**：寻找真实 CRC framing、scrambler、syndrome/编码器和
   线性流水线设计，保持 RTL 与性质自然产生，不能为了求解器改造硬件；
7. **跨拓扑留出验证**：训练 selector 阈值时留出整个拓扑，而不仅仅留出同
   一生成器的随机 seed。

## 15. 最终可形成的论文主张

如果长时限确认成立，最稳健的主张不是“高斯消元普遍优于 CDCL”，而是：

> 传统 AIG/CNF 会隐藏硬件下一状态逻辑中的分模式仿射关系。我们提出一种
> 面向 PDR 的结构恢复与自动呈现方法：从标准 AIGER 输入重建全局或 guarded
> affine transition，根据方程耦合度在 CDCL parity hints 与原生
> XOR/Gaussian reasoning 之间选择，并在模式控制的线性时序数据通路上显著
> 扩展相对通用 IC3 的可解范围。

这条主张同时包含：

- **硬件语义贡献**：从综合后网表恢复线性状态变换；
- **求解器接口贡献**：不是统一 CNF 化，而是结构选择型呈现；
- **模型检测贡献**：机制实际嵌入增量 PDR 查询，而非独立 SAT demo；
- **经验贡献**：给出明确适用域、失效边界及相对 stock rIC3 的可解性结果。

## 16. 这个成果能不能发表

### 16.1 先给结论

**有明确的发表潜力，但当前状态还不是一篇可以放心提交的完整论文。**

更准确地分级：

| 当前成熟度 | 判断 |
| --- | --- |
| 研究想法 | 已经超过概念阶段，有真实实现和强实验信号 |
| workshop/短文 | 补齐正确性验证和核心消融后，有较高可行性 |
| FMCAD/DATE/ASP-DAC 类完整论文 | 需要完整长时限、多家族、真实 RTL 和严格消融 |
| CAV/ICCAD 等强调广泛影响或算法深度的主会 | 还需要更强的机制、外部有效性和与最新方法的系统比较 |

这不是因为目前效果小。恰恰相反，`208/216` 对 `73/216` 以及首批
`12/12` 的 1,800 秒确认都很醒目。真正的问题是：目前最强结果主要来自我们
自己生成的 SAFE 等价性/对齐性质，审稿人会追问这些性质是否恰好暴露了我们
恢复的仿射不变式。

### 16.2 哪些东西本身不够新

以下单项都不能独立支撑论文创新：

- 使用 CryptoMiniSat；
- 开启 Gaussian elimination；
- 将 XOR 作为原生方程提交；
- 从 AIG 中识别标准 XOR gate；
- 在 IC3 中更换 SAT backend。

这些都是已有技术或自然工程组合。论文不能写成“我们发现 CMSat 解 CRC
更快”。CryptoMiniSat 本身已经支持 XOR-CNF 和 Gauss-Jordan 推理，现有
IC3 工作也已经深入优化 SAT 查询或增强 PDR 的证明系统。

### 16.3 真正可能构成新意的组合

当前最有希望的创新点是以下四项作为一个整体：

1. **从综合后的普通 AIGER 恢复完整下一状态仿射方程**，而不是要求用户提供
   XOR-CNF 或特殊 RTL 标注；
2. **恢复 mode/reset/enable 控制下的 guarded affine transition**，把控制
   CNF 与数据通路 GF(2) 推理解耦；
3. **结构驱动自动选择三种呈现**，避免 Gaussian 在稀疏或非线性电路上的
   回退；
4. **直接嵌入 PDR 的增量 translation/lift 查询**，展示其改变的是无界安全
   验证能力，而不只是一次性组合 SAT 性能。

如果文献检索确认没有工作以这一完整形式实现，那么这是一个清楚、可命名、
可复现的技术贡献。比较合适的名字是：

> Mode-Guarded Affine Transition Recovery for PDR

或者：

> Structure-Selected Native Affine Reasoning for Hardware PDR

与相邻工作的边界需要写清：CryptoMiniSat 已经原生支持 XOR 和
[Gauss-Jordan elimination](https://github.com/msoos/cryptominisat)，因此后端
本身不是贡献；GipSAT 工作通过 IC3 查询特性优化 CDCL 的决策变量、heap 和
临时子句，并报告了相对 MiniSat 的明显提升
([Deeply Optimizing the SAT Solver for the IC3 Algorithm](https://arxiv.org/abs/2501.18612))；
PdrER 则通过 Extended Resolution 重编码 PDR proof trace，以构造更短的归纳
证明
([Property Directed Reachability with Extended Resolution](https://arxiv.org/abs/2505.18998))。
我们的差异应落在“恢复 transition 中被综合隐藏的 guarded GF(2) 语义，并
据此选择 SAT presentation”，不能把已有求解器能力包装成新算法。

### 16.4 当前证据的强项

1. **效果不是几个百分点。** 目标域 216 个模型中，单线程 MC-affine 解出
   208 个，MC-XAG 解出 70 个，rIC3-4 解出 73 个。
2. **有同实现消融基线。** MC-XAG 与 MC-affine 使用同一个 PDR 外层，因此
   138 个新增解不能简单归因于“两个工具代码质量不同”。
3. **有强工具基线。** rIC3 使用四副本而 MC-affine 仅用一个 lane，资源口径
   对候选方法并不占便宜。
4. **不是只测目标域。** 159 个 boundary 模型用于观察误用代价；目前相对
   MC-XAG 为 `+16/-1`，表明 selector 至少有一定保守性。
5. **长时限差距已经跨家族出现。** 前 24 个已汇总确认模型覆盖
   frame-align、frame-lock 和 scrambler；MC-affine 全部解出，rIC3-4
   全部达到 1,800 秒时限。其中 12 个 frame-align 的 MC 时间为
   0.52--6.54 秒。
6. **机制可解释。** 每个模型都会输出选择分支、coverage、rank、support 和
   guarded mode 数据，不是黑箱模型选出的配置。

### 16.5 审稿人最可能提出的质疑

#### 质疑一：benchmark 是自己造的

这是当前最大的风险。生成模型有现实结构含义，但仍可能被认为是为了
Gaussian 量身定做。必须增加独立来源的 RTL：真实 CRC framing、网络
scrambler、ECC syndrome 或公开通信 IP，保存来源、revision、综合脚本和
AIGER hash。

回应不能只是“CRC 在现实中有用”，而应该是：

```text
公开 RTL 原本就具有该结构
-> 我们不改 RTL，只综合为标准 AIGER
-> selector 自动识别
-> 相同性质下产生稳定提升
```

#### 质疑二：性质是否过于容易或一阶归纳

首批 1,800 秒确认的 MC 结果深度为 1。这证明表示差异可以造成巨大求解边界，
但也会让审稿人怀疑：是不是我们直接恢复了一个本来就等同于性质的线性
不变式，而 rIC3 只是没有看见。

这仍然可以是“transition presentation”的有效结果，但若要成为更强的 PDR
论文，至少应加入：

- 需要多个 frame 才收敛的 lock/recovery 性质；
- 部分状态不可观测、必须学习中间 lemma 的性质；
- 相同数据通路上的 SAFE 和 UNSAFE 性质；
- Gaussian 只改善一部分查询，而非预处理后立即结束的模型。

#### 质疑三：提升来自哪一项

完整论文必须做因子消融，至少包含：

| 配置 | 回答的问题 |
| --- | --- |
| MC-AIG/CaDiCaL | 不恢复 XOR 时如何 |
| MC-XAG/CaDiCaL | 仅恢复 XOR gate 是否足够 |
| CMSat native XOR、Gauss off | 原生表示本身贡献多少 |
| CMSat native XOR、Gauss on、无 summary | 高斯处理局部门贡献多少 |
| global summary | 完整状态方程贡献多少 |
| guarded summary | mode 分解额外贡献多少 |
| auto selector | 自动方法是否接近 oracle 且控制回退 |

当前历史实验包含其中一些配置，但 375 模型主表没有完整地在同一协议下报告
全部消融。投稿前需要统一实验口径。

#### 质疑四：阈值 32、75% 和两个 control 从哪里来

如果阈值是在同一批测试数据上反复调出来，再在同一批数据上报告结果，会有
过拟合嫌疑。需要冻结：

- development families：用于选择阈值；
- held-out topologies：整个电路拓扑不参与调参；
- external RTL：完全独立验证。

消融应给出阈值附近曲线，而不是只报告最终最优点。

#### 质疑五：summary 是否可靠

0 个结果冲突只是经验信号，不是 soundness 证明。正式实验应：

- 对所有启用 guarded summary 的模型运行等价 SAT 检查；
- SAFE 输出可独立检查的不变式；
- UNSAFE 输出可重放 witness；
- 在论文中给出 guarded 编码等价性的简短证明。

#### 质疑六：rIC3 对 LFSR 的 ERROR

这不能算 timeout 或 candidate win。当前分析已经排除，但论文表格需要单列
`unsupported/error`，不能和未解混在一起。

#### 质疑七：只和一个强基线比较是否足够

rIC3 是很好的主要基线，但最好再加入：

- MC 自身严格消融，隔离算法因素；
- 至少一个其他公开 PDR/IC3 实现或比赛配置；
- 如果输入流程允许，加入支持 XOR/SMT 的相关求解路线。

目标不是堆很多工具，而是防止结论只依赖 rIC3 的一种 AIG 编码策略。

### 16.6 最低可发表版本

一个较稳妥的短文或 workshop 版本至少应完成：

1. 30 个 1,800 秒确认全部跑完，并重复一次关键点；
2. guarded summary 对所有确认模型通过等价检查；
3. 在同一协议下完成 `XAG / native-no-Gauss / Gauss-no-summary /
   global / guarded / auto` 消融；
4. 加入至少一个外部真实 RTL 家族；
5. 明确只主张“模式控制线性数据通路”这一适用域；
6. 发布生成器、模型 manifest、hash、命令和原始结果。

如果剩余确认保持当前趋势，这个版本的结果强度是足够的。短文标题不应强调
“全面超越 rIC3”，而应强调“恢复被 AIG 隐藏的 guarded affine transition”。

### 16.7 完整会议论文版本

完整论文建议达到：

1. 至少 3--4 个不同目标家族在 1,800 秒下稳定成立；
2. 至少 2 个来自独立公开 RTL，而非本项目生成器；
3. 有一组多 frame、非一阶归纳性质；
4. 有 SAFE/UNSAFE 两类性质，或明确解释方法主要针对 SAFE proof；
5. selector 在 held-out topology 上仍能保持大部分 oracle 收益；
6. 给出 SAT 内部统计：Gaussian rank、deduction、conflict、propagation；
7. 给出 PDR 外部统计：frame、CTI、core、lemma、push；
8. 解释深层情况下何时关闭或避免 Gaussian；
9. 完整证书/反例验证和内存数据；
10. 与 stock rIC3 及至少一个补充基线进行等资源比较。

达到这些条件后，论文就不再是“一个特殊 benchmark 上 CMSat 很快”，而是：

> 一种从通用硬件输入自动恢复结构、选择证明表示、扩展 PDR 可解域的方法。

### 16.8 建议的论文结构

1. **Introduction**：AIG 隐藏线性状态更新，通用 CNF-PDR 无法利用；
2. **Background**：PDR、AIG/XAG、XOR-CNF、Gaussian；
3. **Motivating Example**：enable 控制的 CRC/线性状态机；
4. **Affine Recovery**：全局符号传播、rank 和 support；
5. **Guarded Recovery**：control 选择、模式枚举和等价性；
6. **Adaptive Presentation**：三路 selector 与 PDR 集成；
7. **Evaluation**：主结果、消融、外部 RTL、长时限、机制指标；
8. **Limitations**：非线性逻辑、模式爆炸、深层 Gaussian 退化；
9. **Related Work**：XOR-SAT、CryptoMiniSat、SAT-aware IC3、结构化证明；
10. **Conclusion**：限定在 mode-controlled affine datapath，不做普适宣称。

### 16.9 最诚实的当前判断

现在已经可以说：

> 我们找到了一个效果很大、机制清楚、实现完整的特定硬件验证结构域。

现在还不能说：

> 我们已经证明该方法能普遍提升硬件 PDR，或已在广泛真实设计上突破 rIC3。

两者之间缺的不是继续盲目扩大生成样本，而是三件高价值工作：完成跨家族
1,800 秒确认、补真实 RTL、补完整因子消融。只要这三项中前两项保持目前的
强信号，这项工作就值得写成论文。

## 17. 局部 XOR 岛压缩

全局 next-state 仿射判定要求完整状态转移可写成 GF(2) 线性式，适用范围较窄。
现在增加了 maximal private XOR-island 提取：即使整个电路不是全局仿射，也能
把没有外部 fanout 的局部二元 XOR 树改写成一条宽 parity equation。

该改写提前消去只服务于 XOR 树的辅助变量，直接减少 CryptoMiniSat Gaussian
矩阵的行、列和消元工作。共享 XOR 输出会被保留为 boundary，因此不会破坏树外
逻辑；确认运行还可以通过独立 SAT mismatch 查询检查每条摘要。

独立公开 CRC32C target 上的 5-seed 中位时间从 4.012 秒降至 0.515 秒，约
7.8x，且 12 个公开 CRC/LFSR/scrambler RTL 回归无结果分歧。这个结果支持
“仿射数据通路中的局部辅助变量压缩”，不扩展为任意电路或 HWMCC 普遍提升。
完整算法、表格和复现方式见 `XOR_ISLAND_COMPRESSION_REPORT_ZH.md`。
