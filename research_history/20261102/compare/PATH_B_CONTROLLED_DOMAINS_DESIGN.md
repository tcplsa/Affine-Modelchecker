# Path B: Controlled XOR / Arithmetic / Cryptographic Domains — Analysis and Design

> 补充并具体化 `HARD_3600_FOLLOWUP_PLAN.md` 中的 Path B（B0–B4）。
> 定位：在 Path A（真实 HWMCC 家族）可行性差、缺乏可解释性之后，用完全可控、
> 可复现、可干净归因的生成域重新建立"native XOR / 表示呈现影响 PDR 性能"的
> 因果证据链。

---

## 0. 为什么转向 Path B（Path A 的瓶颈）

`HARD_3600_FOLLOWUP_PLAN.md` 的已完成实验已经反复出现三类信号：

1. **机制混杂，难以推广**。15 个 MC-AIG 突破分成四组（浅层 UNSAFE、depth-1 SAFE、
   多帧 SAFE、深度 65 的 `6s151`），XAG 只增加 5 个 union solves。没有一个单一
   XAG/CNF-size 解释能覆盖它们。真实 HWMCC 模型是多因子耦合的（控制状态 +
   数据通路 + 协议状态 + 深时序），机制无法从模型名或家族名上分离。
2. **大量候选只有"进度改善"而无新解**。distance-MIC、obligation order、
   cross-property transfer 等屏幕反复出现"materially deeper frame 但零 solve"。
   深度推进 ≠ 收敛，无法作为覆盖结果发表。
3. **缺乏可控性与可复现性**。真实模型来源多为黑盒（无公开 RTL），无法精确控制
   XOR 密度、位宽、进位结构、流水线级数；`2020__zipcpu-zipmmu-p26` 的
   4.93s 相位多样性结果在 1,200s 屏幕上不复现，说明真实模型受调度/种子噪声
   支配，因果解释脆弱。

**Path B 的回答**：如果无法在真实模型上获得干净的因果，就**自己构造**困难域——
生成器精确控制每一个结构参数，从而允许：

- 逐因子消融（一次只变一个变量）；
- 可复现的缩放边界（宽度/深度扫出相变区间）；
- 在同一套电路上做"表示 vs 求解器 vs 预处理"的分解；
- frozen-query replay 把"内部 SAT 成本"与"外部 PDR 轨迹"分开。

---

## 1. 目标与定位

> 在受控的顺序安全验证家族上，找到 stock rIC3-4 在 3,600s 稳定失败、而某个候选
> （native XOR 方程 / XAG 呈现 / 自适应后端）稳定求解的连续参数区间，并用可测量
> 的仿射秩、XOR 传播、Gaussian 矩阵、PDR 轨迹指标解释该区间。

- **不是** 声称 native XOR 普遍更快。
- **是** 在宽度/深度/结构的连续区间上给出一个**可解释、可复现、可缩放**的因果
  边界（类似 HWMCC 里 AES/CRC 类任务上的"XOR 表示何时救场"）。
- 生成案例**不得**计入 Path A 的 HWMCC 求解数表格（两条路径证据分开）。

### 与 Path A 的关系

| 维度 | Path A | Path B |
| --- | --- | --- |
| 电路来源 | HWMCC 真实/生成模型 | 自建生成器（完全可控） |
| 可解释性 | 差（多因子耦合） | 好（单因子消融） |
| 可复现性 | 受调度/种子噪声影响 | 确定性生成器 + 哈希 |
| 缩放边界 | 难（无受控参数） | 易（宽度/深度扫参） |
| 归因手段 | 弱 | frozen replay + factorial |
| 对论文 | 相关性证据 | 因果 + 机制证据 |

---

## 2. 工具链能力盘点（已有资产）

| 工具 | 输入格式 | SAT 后端 | native XOR | Gaussian | 备注 |
| --- | --- | --- | --- | --- | --- |
| `rIC3`（Rust） | AIGER(AAG/AIG), BTOR2 | CaDiCaL | 仅结构识别（`--aig-encoding native/xag/aig`） | ✗ | stock rIC3-4 基线；有 BVE order、portfolio |
| `Modelchecker`（C++） | AIG | CaDiCaL / MiniSatSimp | aig2xag 结构 XAG，**非方程** | ✗ | 四线程 portfolio；已有 `aig2xag`、BVE、phase 等大量变体 |
| `blif/`（Python PDR） | BLIF | **CryptoMiniSat 5.14** / MiniSat | ✅ `add_xor`（原生 XOR 方程） | ✅（`GaussConf` 存在） | `cmsat_wrapper.cpp` 已封装 `cmsat_add_xor_gate`、`cmsat_add_xor_clause_lits`、`cmsat_set_seed` |
| `sat_query_replay` | 查询流 | CaDiCaL | ✗ | ✗ | 已有 frozen-query replay 基础设施 |
| `aigtoaig` | AIG | — | — | — | AIG↔AAG 转换 |

**关键差距（Path B 需要补齐的工程）**：

1. **顺序电路生成器**（完全缺失）——需要输出至少 AAG（rIC3/MC 用）与带 XOR
   标记的 BLIF（blif/CryptoMiniSat 用）。
2. **CryptoMiniSat wrapper 未暴露 Gaussian 配置**——`GaussConf` 类在
   `solverconf.h` 中（`autodisable`、`min_matrix_rows`、`max_matrix_columns` 等），
   但 `cmsat_wrapper.cpp` 没有对应 `extern "C"` 接口。B2 需要能开关 Gaussian。
3. **frozen-query replay 只支持 CaDiCaL**——B2 需要在 CryptoMiniSat 上 replay
   同一查询流（含 XOR 方程），需要扩展 replay 工具或新增 CMSat replay 通道。
4. **blif 流程缺少可用的 PDR 统计遥测**——`PDRblif.py` 有 `Log`（conflict、time
   等）但未按查询角色/帧输出结构化 JSON；B2 归因需要每查询的
   conflicts/decisions/propagations/XOR-propagations/Gaussian-rank。
5. **rIC3 无原生 XOR 方程**——rIC3 的 `native` 只是结构 XOR 识别后的 CNF 优化
   编码，不是 CryptoMiniSat 式方程。因此"原生方程"的唯一现成载体是
   `blif/` + CryptoMiniSat。B3 的集成要决定：把 CryptoMiniSat 作为 MC 的
   可选 SAT 后端（最大工程量），还是以"XAG 结构呈现 + 有限 Gaussian lane"
   作为更轻的集成点。

---

## 3. B0 — 顺序电路生成器设计

### 3.1 核心数据结构

生成器以**门级网表**为中间表示（不依赖任何输出格式），每个门带类型标签：

```
Gate ::= And(a, b) | Xor(a, b) | Or(a, b) | Not(a)          # 组合
        | Latch(name, init_value, next_signal)               # 时序
Bad :=  bool expr over latches (可多个属性)
Constraint := bool expr (可选)
```

然后**多格式导出**：

- **AAG**（ASCII AIGER）：rIC3 / MC 用。XOR 作为结构保留（rIC3 `native`/
  `xag` 编码可识别；MC `aig2xag` 可识别）。
- **BLIF**（.blif）：blif/CryptoMiniSat 用。`.names` 块明确标记 XOR（与
  `blif_output.py` 的 `_split_names_to_ands_xors` 识别逻辑一致），从而 PDR 里
  走 `add_xor`（原生方程）。
- **BTOR2**（可选）：rIC3 的 word-level 前端（`wlkind`/`wlbmc`）对照用。

同一网表导出三种格式必须保证**轨迹等价**（随机仿真差分校验，复用
`fuzz_differential.py` 思路）。

### 3.2 生成器家族与参数

每个家族一个参数化模板，输出确定性网表 + 合成清单（参数、seed、哈希）。

| 家族 | 关键结构 | 可扫描参数 | 困难来源 |
| --- | --- | --- | --- |
| **仿射/LFSR/CRC/parity** | `x' = A x ⊕ b`，LFSR 本原多项式，CRC 校验，parity 树 | 位宽 n、反馈多项式、CRC 生成多项式、XOR 链深度 | 深度仿射锥 → XOR 传播/Gaussian 应该强 |
| **加法器族** | ripple / carry-lookahead / carry-save / prefix（Brent-Kung/Kogge-Stone）/ modular | 位宽 n、进位结构类型、流水线级数 | 进位链的 AND 稠密区 vs 逐位 XOR 区混存 |
| **乘法器/MAC** | array / Booth / Wallace 树，流水线 | 位宽 n、partial-product 结构、流水线级数 | 大量 AND partial product + XOR 归约 |
| **AES 线性层 + key schedule** | MixColumns + ShiftRows（MDS 矩阵），key-schedule | 列宽、轮数、流水线 | 仿射线性层（XOR 密集）+ 顺序状态 |
| **ARX**（与纯仿射分开） | TEA/XTEA 类：加-旋转-XOR | 位宽 n、轮数 | 加法进位与 XOR 混合，**非线性** |

**约束**：属性必须需要**顺序归纳**，不能只是组合等价（否则 BMC 一步解决，
IC3 无贡献）。每个属性给出期望结果（SAFE/UNSAFE）由独立参考（BTOR2 语义或
简单 BMC）预验证。

### 3.3 属性设计（示例，需要顺序归纳）

- **LFSR**：全零状态不可达（SAFE）；或特定非零态在 k 拍后必达（UNSAFE，需要
  BMC 深度依赖）。属性落在仿射锥上。
- **累加器**：`acc[n] == Σ in[0..n] mod 2^w` 归纳不变量（SAFE）。
- **乘法器流水线**：流水线输出 == 参考乘法（需要多拍对齐归纳）。
- **CRC**：对给定消息的 CRC 校验值不变量。
- **AES MixColumns**：列字节间的线性关系（MDS 性质）不变量。

### 3.4 可复现性清单

每次生成输出 `manifest.json`：

```json
{
  "family": "lfsr", "width": 64, "poly": "0x...", "pipeline": 1,
  "seed": 730001, "expected": "SAFE",
  "aag_sha256": "...", "blif_sha256": "...", "btor2_sha256": "...",
  "stats": {"xor_density": 0.42, "bad_cone_xor_density": 0.9, "latches": 64, "ands": 1234}
}
```

生成器必须是**纯函数**（seed → 网表），禁读任何候选结果文件（与
`BVE_AIG_HARD_DOMAIN_PREREGISTRATION.md` 的预注册纪律一致）。

---

## 4. B1 — 相变定位（stock rIC3 基线扫描）

目标：为每个家族找到 stock rIC3-4 的**超时边界**，选定一个连续参数区间作为
候选域。

协议（复用 HARD_INSTANCE_BREAKTHROUGH_PLAN 的分级限制）：

1. **300s 快筛**：丢弃 trivial 尺寸（双方都秒解或都无法解析）。
2. **1,800s**：围绕首个超时边界加密扫描。
3. **3,600s**：对边界两侧做最终分类，四个默认 lane 复现。

选择准则：

- 一个**连续参数区间**上 stock rIC3-4 在 3,600s 稳定失败（例如 LFSR
  width ∈ [32, 128] 全部超时，而 width ≤ 16 秒解）；
- 至少保留一个更大尺寸和一个不同拓扑作为 **held-out**（训练/验证分离，
  禁止随机打散同一生成器的连续尺寸区间）；
- 记录失败签名（帧深度停滞 / 高冲突 / 大 lemma），用于后续对照候选的
  改进是否针对该签名。

输出：`pathb_phase_boundary.tsv`（家族、参数、baseline 状态、失败签名）。

---

## 5. B2 — 归因实验设计（XOR 优势从哪来）

在 B1 选定的相变区间上，对**同一网表**做 factorial，分离三个候选解释：

> ① 更强的 CDCL 后端；② 原生 XOR 传播 + Gaussian 消除；
> ③ 预处理或 PDR 查询轨迹变化。

### 5.1 因子表（每格同一电路、同 seed、同超时）

| 因子 | Levels |
| --- | --- |
| SAT 后端 | MiniSat / CryptoMiniSat（在 blif 流程内切换） |
| XOR 表示 | CNF-lowered（AND 展开）/ native XOR 方程（`add_xor`） |
| 预处理 | off / on（`cmsat_simplify` / MiniSatSimp eliminate） |
| Gaussian | off / on（需先扩展 wrapper 暴露 `GaussConf`） |

纯结构对照组（rIC3 / MC）：同一 AAG 在 `--aig-encoding aig|native|xag` 上，
与 blif 流程结果并排，识别"结构 XAG 呈现"与"原生方程"是否是同一件事。

### 5.2 frozen-query replay（分离内部 SAT vs 外部轨迹）

复用 `sat_query_replay` 的思路，但**扩展支持 CryptoMiniSat**（含 XOR 方程）：

1. 在一种配置下跑 PDR，把**每个 SAT 查询**（frame/lift/MIC/CTG/push 角色 +
   原始子句 + assumptions）记录成流；
2. 用不同后端/表示/预处理**重放同一查询流**；
3. 对比每查询的 conflicts / decisions / propagations / XOR-propagations /
   Gaussian 矩阵秩与大小 / UNSAT core 大小。

判定：

- 若重放下成本显著更低而 PDR 轨迹（查询序列、帧深度、lemma 流）不变 →
  机制是"**内部 SAT 成本**"；
- 若轨迹本身改变（不同 SAT 模型/核 → 不同 lemma → 不同帧推进）→ 机制是
  "**外部 PDR 轨迹**"；
- 两者都变 → 交互，需分阶段贡献。

### 5.3 观测指标（每条查询/每帧）

- conflicts, decisions, propagations；
- XOR-propagations / conflicts, Gaussian 矩阵数、行/列、秩（CMSat 侧）；
- 帧深度、CTI 数、MIC 调用数、push 失败数、lemma 尺寸/宽度、lemma 重复率；
- 内存与 CNF 扩展（预处理 on 时）。

### 5.4 成功判据

> 存在一个**连续参数区间**，其中 stock rIC3-4（或 CNF-lowered 对照）3,600s
> 超时，而某个配置稳定求解；且归因实验能指出是②（原生 XOR/Gaussian）还是
> ①/③ 主导——用测量到的仿射秩、XOR 传播量、Gaussian 秩变化来解释，而不是
> 只写"电路里含 XOR 门"。

---

## 6. B3 — 最小有效机制的集成

按实现成本递增，选第一个能复现 B2 机制的集成点：

1. **一个 native-XOR / CryptoMiniSat lane** 放进四线程 MC portfolio
   （`blif/` 已验证 add_xor 路径；成本最低）；
2. **查询自适应后端选择**：按当前查询的仿射锥密度，在 CNF 与 native-XOR
   方程间切换（对应 `xag2xag` 的 `xor_policy` 与 B2 的密度信号）；
3. **受控双编码**：同一查询同时暴露 CNF 与 native XOR（CMSat 支持）；
4. **XOR-aware 核/泛化**：在 PDR 泛化时用仿射关系约束 literal 顺序。

纪律（沿用 HARD_3600_FOLLOWUP_PLAN）：

- 固定四线程预算；候选与 MC-AIG（或 stock rIC3-4）**等预算**直接对比；
- 报告 union coverage 与 lost solves；
- 机制按结构/在线状态选择，**不按模型名**。

先以 MC 作为第一个受控演示（表示与线程分配最易隔离），机制验证后再转移到
rIC3——只有两个工具跨过同一缩放边界时才算强结果。

---

## 7. B4 — 确认与报告

主图：solved / runtime vs 宽度或流水线深度（整条 sweep，含双方都解与都超时
的区间）。

- held-out 宽度/拓扑验证（不参与 B1 选择）；
- 边界点独立进程重复一次；
- SAFE 证书 / UNSAFE witness 独立验证（`verify_invariant.py`、
  `certificate_check`）；
- 报告区间两侧 + 区间内，用 B2 的测量指标解释为什么边界在这里。

成功定义（与 HARD_INSTANCE_BREAKTHROUGH_PLAN 一致）：

- 最小研究信号：一个持久困难区间，候选稳定求解且有匹配机制解释；
- 可发表结果：连续区间 + 两个工具跨越同一边界 + 可测量解释。

---

## 8. 执行顺序与工程清单

阶段 0（先行，纯工程，无结果可 bias）：
- 写生成器（家族 1–2：LFSR/仿射 + 加法器族），AAG + BLIF 双导出 + 差分校验；
- 扩展 `cmsat_wrapper.cpp` 暴露 Gaussian 开关与 XOR/Gaussian 统计；
- 给 `PDRblif.py` 加结构化查询级遥测（JSON）。

阶段 1（B1）：300s/1,800s/3,600s 分级扫描，选相变区间 + held-out。

阶段 2（B2）：在选定区间做 factorial + frozen replay（先 CaDiCaL，再补
CryptoMiniSat replay）。

阶段 3（B3）：按成本递增集成，先单 lane，再自适应。

阶段 4（B4）：sweep 曲线 + 证书验证 + 双工具边界对照。

每阶段产出独立 TSV/JSON 与哈希冻结，禁止回溯修改选择规则。

---

## 9. 与 Path A 的协调

- 若 Path B 在 AES/CRC/LFSR 上发现机制，可作为 Path A 中同类家族的**受控对照**
  （例如某 HWMCC 模型 bad 锥 XOR 密度 ≥ 阈值时，候选是否同样成立）；
- 生成案例**永不**并入 Path A 的 solved-count 表；
- 两者共享插桩（查询级遥测、replay、证书验证），但不共享证据。
