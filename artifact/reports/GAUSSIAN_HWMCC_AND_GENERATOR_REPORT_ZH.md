# rIC3 难题家族、仿射样例生成方法与 Gaussian 实验报告

## 1. 结论先行

本报告区分三个不能混用的数据域：

1. **HWMCC 真难题域**：590 个 stock rIC3 四副本在 3,600 秒内未解的模型；
2. **仿射目标域**：216 个预先归入 CRC、scrambler、syndrome、LFSR 等
   线性数据通路的生成模型；
3. **长时限确认域**：从 120 秒筛选中按家族和规模分层抽出的 30 个模型，
   再用 1,800 秒运行 MC-affine 单线程和 stock rIC3 四副本。

当前最可靠的判断是：

- Gaussian **不是** HWMCC 的普适增强。在已完成的 1,398 个 HWMCC 探测中，
  与 rIC3-3,600 秒真难题相交的 331 个模型只解出 3 个，而且都已被 MC-AIG
  解出，新增覆盖为 0。
- Gaussian 在预定义的仿射/分模式仿射硬件域中有非常大的、可重复的优势。
  120 秒目标域中 MC-affine 单线程解出 208/216，rIC3 四副本解出 73/216；
  排除 rIC3 不支持的 27 个 LFSR 模型后，MC 对 rIC3 真超时新增 114 个解，
  只丢 1 个 rIC3 解。
- 30 模型的 1,800 秒确认已经全部完成：MC-affine 为 30/30 SAFE，rIC3-4
  为 2/30 SAFE、28/30 TIMEOUT。该确认集是按 120 秒结果分层选择的强信号，
  不是随机全量样本，不能把 28/30 直接外推成任意硬件上的胜率。

因此研究主张应是：**自动识别具有高覆盖仿射 next-state cone 的顺序数据
通路，并为这些模型选择原生 XOR + Gaussian 后端**，而不是“用 Gaussian
替换一般 PDR 的 SAT 求解器”。

---

## 2. rIC3 在 HWMCC 上没有覆盖哪些家族

### 2.1 冻结难题集

筛选输入为 604 个 rIC3 在 1,800 秒实验中未解的候选。stock rIC3 四副本
统一延长到 3,600 秒后：

- 14 个在 1,800--3,600 秒之间解出；
- 590 个仍未解，构成本报告的真难题集；
- 年份分布为 2015: 196、2017: 54、2019: 68、2020: 68、2024: 119、
  2025: 85。

机器提取器给出 217 个 family 标签，但这个数字不能按字面理解。例如：

- 97 个 `6s...` 模型被命名规则拆成了 97 个 singleton family，语义上属于
  同一个 6s 工业验证套件；
- 28 个 `ILA_Flute/Piccolo/Ridecore_*` 属性各自形成一个标签，语义上都是
  处理器指令/实现一致性检查；
- 22 个 `beem*` 模型形成 16 个标签，来源都是 BEEM 并发软件模型；
- 50 个 `yosyshq_appnote_*` 全部属于同一来源组，只是覆盖 CV32E40X、VeeR
  和 VeeR-AXI 的不同性质。

完整的 217 标签、数量、年份和静态结构数据见：
`results/mc_ric3_hard_global_v1/hard_family_atlas.tsv`。

### 2.2 最大的机器标签

| 标签 | 数量 | 设计/任务含义 | 证据强度 |
| --- | ---: | --- | --- |
| `oski` | 81 | OpenSPARC T1 的 CPU-cache crossbar (CCX) 端到端安全检查，包含多核、L2、IOB、FPU 间并发仲裁与 FIFO | 官方 HWMCC 说明明确 |
| `yosyshq_appnote_` | 50 | CV32E40X、VeeR、VeeR-AXI 等 RISC-V 处理器核的大量安全性质 | 本地原始目录明确 |
| `cal` | 27 | `goel/industry/cal*` 匿名工业电路；公开数据没有足够 RTL 语义，不能进一步断言 | 来源目录明确、功能不透明 |
| `arbitrated_top_n` | 25 | 参数化多端口仲裁存储/FIFO，参数包含端口数 `n`、数据宽度 `w` 和深度 `d` | 文件名与结构推断 |
| `picorv` | 24 | PicoRV32 RISC-V 核，包括寄存器性质和多种 mutation/bug 版本 | 模型名明确 |
| `Problem` | 23 | RERS 2012/2018 反应式系统挑战模型转换出的安全性质，更接近软件状态机而非普通 RTL 模块 | 本地路径明确 |
| `oc` | 19 | OpenCores 8051 微控制器，性质涉及 accumulator、IRAM、PC 等 | 模型名明确 |
| `intel` | 14 | Intel 提交的闭源/匿名硬件安全实例 | HWMCC 来源明确，具体功能不公开 |
| `circular_pointer_top_w` | 12 | 参数化 FIFO/环形缓冲区指针管理 | 文件名与参数明确 |
| `mul` | 12 | 乘法器或乘法数据通路性质 | 名称明确，微结构不透明 |
| `zipcpu` | 12 | ZipCPU 的 MMU 及相关处理器性质 | 原项目和模型名明确 |
| `vgasim_imgfifo` | 11 | VGA 帧缓冲读取链路中的 Wishbone 到像素侧异步 image FIFO | 原 RTL 项目明确 |
| `pals_lcr` | 9 | PALS 框架下的 LCR 环形 leader-election/分布式协议模型 | 名称与 PALS 来源推断 |
| `level_` | 9 | `xsokoban` 关卡编码，属于规划/状态可达性问题 | 本地路径明确 |
| `a` | 8 | HKU/HKUST X-EPIC 套件的安全性质；公开命名不足以恢复具体模块语义 | 来源目录明确、功能不透明 |
| `VexRiscv` | 7 | VexRiscv 处理器寄存器/流水线性质 | 模型名明确 |
| `rast` | 7 | RAST 套件属性；当前只有 AIG 和属性编号，具体 RTL 功能尚未可靠恢复 | 功能不透明 |
| `pgm_protocol` | 5 | 程序/协议状态机的安全性质，含不同串行化和函数式变换版本 | 模型名明确 |
| `shift_register_top_w` | 5 | 参数化移位寄存器/FIFO 存储结构 | 文件名明确 |
| `rocket_` | 4 | Rocket RISC-V 处理器属性 | 模型名明确 |

前 12 个标签覆盖 310/590，即 52.5%；前 20 个覆盖 364/590，即 61.7%。
剩余部分是很长的尾部：178 个机器标签只有一个模型。

### 2.3 按实际用途重新归类

比 217 个名字更有意义的语义分类如下。

#### A. 处理器、缓存和片上互连

包括 `oski`、YosysHQ appnote、`picorv`、`oc8051`、`zipcpu`、
`VexRiscv`、`rocket`、`ridecore`、Intel 和 ILA Flute/Piccolo/Ridecore。
这些模型难在：状态多、控制分支多、缓存/MMU/总线并发强，而且安全性质只触及
大设计的一部分。Oski 官方说明确认其来自 OpenSPARC T1 的 CCX，并包含 11 个
并发 arbiter 和大量 FIFO；这类问题天然不是纯仿射系统。

#### B. FIFO、指针、仲裁和通信控制

包括 `arbitrated_top_n`、`circular_pointer_top_w`、
`shift_register_top_w`、`vgasim_imgfifo`、`ponylink`、`fifo`、`pc_sfifo_`。
它们常包含读写指针回绕、满空判断、跨时钟握手、总线 back-pressure 和仲裁。
这类电路可能有 XOR/计数器，但主要难点通常是控制状态组合，而不是线性方程组。

#### C. 算术与算法状态机

包括 `mul`、`gcd`、`lcm`、`egcd`、Newton sqrt、`prodbin`、`cal`，以及
RERS、Dijkstra、Fermat、Sokoban 等算法/软件状态机。部分模型静态 XOR 密度
较高，但“affine-heavy”只表示识别到较多 XOR，不代表所有 latch 的下一状态
能组成可直接高斯消元的线性系统。

#### D. 并发软件与分布式协议的硬件化编码

包括 BEEM、RERS、PALS、Lamport、leader election、`pgm_protocol` 等。
它们使用 AIGER 承载状态转移系统，但研究对象不一定是现实 RTL 数据通路。
BEEM 模型是从显式状态并发软件基准翻译到 BTOR/AIGER 的，这一来源在 HWMCC
官方说明中有明确记录。

#### E. 匿名工业与深度变换实例

包括 6s、Intel、`cal`、`bob` 以及部分只有编号的实例。HWMCC 文献说明，6s
中有不少是工业验证流程中高度变换后的子问题，例如顺序冗余消除过程中产生的
安全或顺序等价检查。缺少 RTL 时，不能仅凭 AIG 反推出“它在现实中是什么
模块”；报告只能可靠描述其规模、cone 和求解轨迹。

### 2.4 对 Gaussian 方向的含义

590 个真难题的静态结构分层为：

| 静态类 | 数量 |
| --- | ---: |
| mixed-control-data | 354 |
| affine-heavy | 170 |
| state-heavy | 49 |
| very-large | 17 |

这里的 `affine-heavy` 不能直接当作 Gaussian 适用标签。Gaussian 路线需要的
更强条件是：当前性质相关的 next-state cone 在全局或少量 guard 模式下可表示
为高覆盖 GF(2) 方程组。HWMCC 探测已经验证，单纯看到 XOR 多并不足以产生
额外覆盖。

---

## 3. Gaussian 样例是怎样生成的

### 3.1 统一生成流程

生成器位于 `pathb/families/`，流程为：

1. 用 `Netlist` API 显式建立 inputs、latches、AND/XOR/OR 和 bad property；
2. 同时输出普通 AAG 和保留 XOR 的 BLIF；
3. manifest 保存参数、预期 SAFE、结构统计和 SHA-256；
4. 重新生成并检查 hash 和门统计，防止实验文件漂移；
5. 每个模型执行多条固定随机顺序仿真，检查是否意外到达 bad；
6. 求解时从同一 AAG 输入恢复 XOR/仿射结构，生成器不会把内部语义直接传给
   求解器。

这不是“随机生成一堆 XOR 门”。每个 family 都有固定的状态转移和安全性质，
随机 seed 主要决定初态、满秩矩阵或 parity support，不改变任务类型。

### 3.2 主要目标家族

#### CRC equivalence

维护两份相同 CRC 状态：

- 左侧逐 bit 执行反馈移位；
- 右侧先在 GF(2) 上符号展开若干 bit，再实例化为并行 XOR matrix；
- bad 表示两份状态不同。

使用 CRC-8、CRC-16-CCITT、CRC-32 等多项式，改变状态宽度、每周期数据位数和
展开步数。这对应现实硬件中串行参考实现与高吞吐并行 CRC 的等价检查。

#### CRC frame-align

两份 CRC 从不同的任意状态开始。`start_of_frame` 同时把两份状态装载为标准
seed，此后在任意 `valid/data` 序列下必须保持相等。每个 next-state bit 实际是：

```text
sof ? reset_seed : (valid ? crc_update(state, data) : state)
```

因此它不是全局线性，而是在 `sof`、`valid` 四种模式下分别仿射，正好测试
guarded-affine 恢复。

#### CRC frame-lock

在 frame-align 上增加 block-lock 控制器：连续若干合法 header 后获得 lock，
link loss 会失锁并重新训练。性质为：`locked -> serial_crc == matrix_crc`。
它把现实链路恢复控制和线性 CRC 数据通路放在一起，用来测试控制深度增加后
Gaussian 是否仍有价值。

#### 64b/66b scrambler

使用 `1 + x^39 + x^58` 自同步 scrambler：

- `scrambler_equiv` 比较逐 bit 实现和并行 matrix 实现；
- `scrambler_recovery` 让收发历史从不同状态开始，检查接收端经过 58 bit 后
  自动同步并正确恢复 payload。

该多项式和 58-bit history 来自 64b/66b PCS，而不是为了高斯实验任意选择。

#### Syndrome 与 LFSR jump

- `syndrome_equiv` 比较串行 XOR 链和 balanced XOR tree 对同一 parity-check
  matrix 的流式 syndrome 更新；
- `lfsr_jump_equiv` 比较迭代执行 N 次 LFSR 与一次 matrix jump-ahead。

两者分别对应纠错码 syndrome 单元和并行 PRBS/LFSR 状态推进。

### 3.3 机理与边界家族

`affine_phase_sync` 生成确定性的满秩 GF(2) 矩阵。左右两份状态初始差值非零，
one-hot phase 在每一阶段注入预计算 correction，使差值按指定轨迹演化并在
`done` 时恰好变成零。生成器在构造时直接检查：

```text
difference[t+1] = A(difference[t]) XOR correction[t]
```

矩阵要求满秩，且固定 row weight 必须为奇数，避免 all-one null vector。
这个 family 能干净隔离“原生 XOR”与“真正 Gaussian elimination”的差别，
但 correction trajectory 是人为设计的。因此它是合理的因果压力测试，不能
单独声称代表某个具体商用 scrambler 协议。

AES MixColumns、Keccak theta-rho-pi、ARX、adder 和 MAC 等 family 用于边界
测试：AES/Keccak 只保留标准中的线性层；ARX、adder、MAC 则有 carry/AND
非线性，预期不应无条件选择 Gaussian。AES MixColumns 的固定矩阵来自 FIPS
197；Keccak family 明确省略非线性的 chi 和 iota，不能称为完整 Keccak 核。

### 3.4 合理性评价

#### 合理之处

1. **语义真实**：CRC、64b/66b scrambler、syndrome、LFSR jump 和 AES
   MixColumns 都对应现实硬件功能。
2. **变量可控**：宽度、吞吐量、矩阵密度、guard 数和控制深度可独立调整，
   适合寻找 Gaussian 的相变边界。
3. **不是格式特权**：求解器只读取 AAG，再自行恢复 XOR 和仿射 summary。
4. **双实现检查**：多数性质比较串行与并行、serial 与 balanced 等不同拓扑，
   比“永远为真的常量性质”更有意义。
5. **包含负对照**：ARX、adder、MAC、residue 和深层控制模型用于确认选择器
   会回退，而不是只报告有利样例。

#### 局限性

1. 大多数模型由本项目的同一 Python netlist 框架生成，存在共同实现错误风险；
   随机仿真只能发现反例，不能代替独立形式化等价证明。
2. 1,024/2,048-bit 每周期 CRC 或 scrambler 是高吞吐缩放压力点，不一定是
   常见产品配置。多项式和功能真实，不代表所有参数都同样常见。
3. 多数性质是两份实现的顺序等价，覆盖了重要工业任务，但不等于控制器所有
   safety property。
4. `affine_phase_sync` 的难度经过工程化设计，外部有效性弱于 CRC 和 64b/66b。
5. 目前真实 RTL/Yosys 流的样本较少；现有 parallel/serial RTL refinement
   在 120 秒内 CaDiCaL 和 CMSat 都未解，尚未形成现实 RTL 上的新覆盖结论。

所以最稳妥的论文证据结构是：用 phase-sync 做因果消融，用 CRC/scrambler/
syndrome 做应用域，用 HWMCC 负结果限定外部边界。

---

## 4. Gaussian 相对 rIC3 的实验提升

### 4.1 120 秒完整范围

所有 MC 配置为单 lane；`rIC3-4` 是四个 stock rIC3 IC3 副本，共享终止。

| 范围 | 模型 | MC-XAG | MC-affine | rIC3-4 | MC-only | rIC3-only |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 目标仿射域 | 216 | 70 | **208** | 73 | 136 | 1 |
| 边界/非目标域 | 159 | 107 | **122** | 97 | 25 | 0 |
| 合计 | 375 | 177 | **330** | 170 | 161 | 1 |

目标域中有 27 个 `lfsr_jump_equiv` 使 stock rIC3 以 exit code 2 退出，不能
当作 rIC3 超时。排除它们后，公平口径为：

- rIC3 支持的目标模型：189；
- MC-affine 解出 186/189；
- rIC3-4 解出 73/189；
- 两者共同解出 72；
- MC 解出而 rIC3 真超时 114；
- rIC3 解出而 MC 未解 1。

在共同解出的 72 个目标模型上：

- MC/rIC3 端到端墙钟几何均值比为 0.303，即 MC 约 **3.30 倍快**；
- paired median ratio 为 0.631，即中位数约 **1.58 倍快**；
- outcome conflict 为 0。

按应用家族：

| 家族 | MC-affine | rIC3-4 | MC 解出且 rIC3 真超时 |
| --- | ---: | ---: | ---: |
| CRC frame-align | 88/88 | 10/88 | 78 |
| CRC frame-lock | 38/41 | 12/41 | 27 |
| scrambler equivalence | 22/22 | 14/22 | 8 |
| scrambler recovery | 16/16 | 16/16 | 0 |
| syndrome equivalence | 22/22 | 21/22 | 1 |
| LFSR jump | 22/27 | rIC3 不支持 | 不计入 timeout |

### 4.2 1,800 秒分层确认

确认集包含：12 个 CRC frame-align、8 个 CRC frame-lock、6 个 scrambler
equivalence、1 个 syndrome 和 3 个 affine phase-sync。它们在 120 秒筛选时
均为 MC 解出、rIC3 超时，并按模型尺寸均匀抽取；1,800 秒确认允许 rIC3
重新解出，因此不是简单复制 120 秒标签。

最终结果：

| 家族 | 模型 | MC-affine SAFE | rIC3-4 SAFE | rIC3-4 TIMEOUT |
| --- | ---: | ---: | ---: | ---: |
| CRC frame-align | 12 | 12 | 0 | 12 |
| CRC frame-lock | 8 | 8 | 0 | 8 |
| scrambler equivalence | 6 | 6 | 0 | 6 |
| syndrome equivalence | 1 | 1 | 1 | 0 |
| affine phase-sync | 3 | 3 | 1 | 2 |
| **合计** | **30** | **30** | **2** | **28** |

MC 的 30 个运行耗时范围为 0.506--41.553 秒，中位数 0.619 秒，总计
117.44 秒。rIC3 的两个共同解为：

- syndrome：MC 3.014 秒，rIC3 104.131 秒，MC 约 34.5 倍快；
- phase-sync：MC 2.016 秒，rIC3 829.918 秒，MC 约 411.7 倍快。

两个共同解的几何平均 MC/rIC3 比为 0.00838，即约 119 倍快。样本只有两个，
这个时间倍数只能作为描述性结果；主要证据是其余 28 个模型在 1,800 秒形成
稳定覆盖分离。

### 4.3 更严格的 Gaussian 因果消融

CRC-32 frame-align 的两个代表点各运行两次：

- 1x CaDiCaL-XAG：两次均 TIMEOUT；
- 1x CMSat native XOR、关闭 Gaussian：两次均 TIMEOUT；
- 1x CMSat + Gaussian：两次均约 0.50 秒 SAFE；
- stock rIC3-4：两次均 1,800 秒 TIMEOUT。

这说明结果不能只解释成 CMSat 或原生 XOR 语法优势，Gaussian elimination
在该 CRC 查询中是必要处理因素。

`affine_phase_sync` 还有 11 个稳定点进行了两组独立进程确认：每个点的
stock rIC3-4 两次都超时，`3x CaDiCaL + 1x Gaussian` 两次都证明 SAFE。
其中一个点进一步验证了 1x CaDiCaL、4x CaDiCaL 和 1x CMSat-no-Gauss
全部超时，而 1x Gaussian 分别在 61.57 和 56.09 秒完成。

### 4.4 HWMCC 外溢结果

四 lane CMSat/Gaussian 的 HWMCC 探测完成 1,398/1,980 后停止：

- 完成部分中有 331 个属于 rIC3-3,600 秒真难题；
- Gaussian 解出 3 个；
- 3 个全部已由历史 MC-AIG-4 解出；
- 相对 `MC-AIG union MC-XAG` 的新增覆盖为 0。

剩余 582 个未跑模型理论上仍可能出现偶然新增解，因此严格表述是“已完成
部分未观察到额外覆盖”，不是数学证明后续永远为零。但当前信号已经足够否定
继续把四个线程全部投入 Gaussian 的资源配置。

### 4.5 补充 UNSAFE 实验

原 375 模型语料库全部为 SAFE。为检查寻找反例时的行为，后续增加了 48 个
结构配对的 UNSAFE 模型：在 CRC frame-align、64b/66b scrambler 和 streaming
syndrome 的右侧实现中注入一次性 delayed XOR fault，首个 bad 深度固定为
2/8/32/128。全部模型通过门级 witness 仿真；一个 depth-128 syndrome 还由
rIC3 BMC 独立生成了 128 步反例。

30 秒完整拆分结果为：MC-CaDiCaL 42/48、CMSat native XOR no-Gauss 48/48、
CMSat native XOR Gaussian 47/48、summary no-Gauss 48/48、summary Gaussian
48/48、两个深度门控配置均为 48/48，stock rIC3 四副本为 22/48。

因此这批 UNSAFE 结果证明了 MC 的自动表示/后端路线能扩张构造域覆盖，但没有
证明 Gaussian 对反例搜索有贡献：关闭 Gaussian 的 CMSat 已经全部解出，
始终开启反而丢了一个深层 scrambler。详细构造、分层表和局限性见
`UNSAFE_AFFINE_EXPERIMENT_ZH.md`。

---

## 5. 最终评价与下一步

### 已经成立的成果

1. 找到了明确适用域：高覆盖全局/guarded affine next-state 系统；
2. 在 CRC、scrambler、syndrome 和受控 phase-sync 上形成 rIC3-4 无法覆盖、
   MC 单 Gaussian lane 可以覆盖的稳定区间；
3. 用 CMSat-no-Gauss 消融证明关键因素不只是 XOR 表示，而是 Gaussian 推理；
4. 自动选择器可以让非适用模型回退，最新 22 模型 guarded 回归为 22/22
   SAFE，并恢复 1,357/1,408 个 next-state 方程；
5. HWMCC 负结果清楚限定了主张边界，避免把专用方法包装成普适求解器。

### 还不能声称的内容

- 不能声称 Gaussian 普遍优于 rIC3；
- 不能把 30 个筛选确认模型的 28/30 当作随机全量成功率；
- 不能把 phase-sync 单独当作现实工业价值证明；
- 不能声称已经在 stock HWMCC 上增加了覆盖；
- 不能把 UNSAFE 构造域的 48/22 归因于 Gaussian；
- 不能声称深层任意控制逻辑都能由当前最多两个 guard 的方法处理。

### 最有价值的后续工作

1. 从真实开源 RTL 构建独立 CRC、PCS scrambler、FEC syndrome 和 LFSR
   jump-ahead 验证集，经 Yosys/ABC 合成后再运行同一选择器；
2. 对生成模型分层运行 SAT 等价校验或独立 reference implementation，降低
   同一生成框架造成的共同错误风险；
3. 做 property-related partial summary，只摘要 PDR 高频访问的 affine next
   cone，扩大到混合控制/数据设计；
4. 使用在线 Gaussian 收益/成本观测做深层关闭，而不是固定 frame 阈值；
5. 将方法作为一条 specialist lane 接入四线程 portfolio，而非四条 lane 全部
   使用 CMSat/Gaussian。

## 6. 数据与外部依据

本地主要数据：

- `results/ric3_hard_3600_v1/analysis/report.md`
- `results/ric3_hard_3600_v1/analysis/ric3_4_hard_3600.json`
- `results/mc_ric3_hard_global_v1/hard_family_atlas.tsv`
- `results/pathb_affine_full_scope_v1/report_120s.md`
- `results/pathb_affine_full_scope_v1/confirm_1800s.tsv`
- `results/pathb_affine_phase_sync_1800_report.md`
- `results/pathb_real_xor_apps_v1/crc32_gauss_1800_confirmation.md`
- `results/hwmcc_gauss_full_v1/partial_report.md`

外部依据：

- HWMCC 2014/2015 报告（6s 与 Oski 来源）：
  https://fmv.jku.at/papers/HWMCC14-JSAT16.pdf
- HWMCC 2020 benchmark 与一小时竞赛配置：
  https://fmv.jku.at/hwmcc20/
- HWMCC 2024 数据集：
  https://zenodo.org/records/14042523
- ZipCPU 项目：https://github.com/ZipCPU/zipcpu
- Vgasim 项目：https://github.com/ZipCPU/vgasim
- AES FIPS 197：https://csrc.nist.gov/pubs/fips/197/final
- IEEE 64b/66b scrambler polynomial 的公开 PCS 材料：
  https://grouper.ieee.org/groups/802/3/ap/public/sep05/szczepanek_02_0905.pdf
