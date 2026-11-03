电路分析与证明：研究工作流 v1

入口已经接到项目的 C++ 程序：
  ./circuit-analysis-proof --workflow --help

这一版完成的是“安全性质输入→结构事实→候选关系→证明义务→结果验收→对照”
的执行框架。它复用现有研究算法，避免继续为每个例子临时写一套驱动。
原生C++的其它分析接口还没有全部迁移实现；本版不是整核ISA验证完成。
目前拆分的是证明义务，完整转移关系仍保留，不是物理网表切块后的合同替换。

1. 文件与责任

  workflow.cpp/.h       C++98入口，直接传递argv，不拼接shell命令。
  cli.py                prepare/run/compare命令及预算参数。
  problem.py            固定输入、工具配置、源码证据、模型哈希和目标集合。
  analysis.py           依赖图、状态/位宽/自由输入、信号名、固定模型请求。
  feedback.py           选择仍未证明的义务、保留宽寄存器的归纳反例取值。
  runner.py             预算、候选循环、检查顺序、记录、成对对照、断点续跑。
  backends.py           拆分SMT、整体SMT、原版CIll、普通rIC3、反例回放。
  worker.py             受超时和内存限制的SMT工作进程。
  common.py             严格JSON、原子写结果、文件哈希、进程组清理。

候选表达式编译与自动拆分复用 learning/lemma_pilot/ 中已测试的实现，
BTOR到SMT复用 learning/storage_relations/btor_smt.py。
Python部分用于编排外部工具和API；没有把求解算法重新写成另一套C++。

2. 输入与输出协议

准备请求：cap.request.v1，例子见 examples/paired.json 和 examples/counter.json。
  id：样例名。
  scope：原始时钟、复位、环境、性质范围的文字说明。
  input：kind=btor2及path；或kind=rtl、top、files和可选include_files/
         include_dirs/defines。RTL路径相对于请求文件，保留目录结构。
  sources：BTOR场景可额外指定的HDL文件白名单，仅作参考，不能据此宣称等价。
  tools：可覆盖工具路径；默认使用本机已安装的固定工具。

prepare输出一个问题包：
  problem.json：cap.problem.v1，原目标数量、所有输入文件哈希、工具路径、
                前端及来源说明。
  model.btor2：冻结的唯一语义输入。
  symbols.json：cap.symbols.v1，BTOR里实际存在的名字、节点、类型和位宽。
  RTL输入另外保留compile.ys、日志、RTLIL、Yosys JSON及witness map。

执行输出：
  run.json：模型、工具二进制、实现文件哈希、方法和全部预算。
  analysis.json：cap.analysis.v1，结构事实；有模型调用时附实际上下文边界。
  context.btor2.txt/source-context.txt：确实发送给模型的内容。
  round-XX/request.json/response.json/candidate.json：原始调用与候选。
  round-XX/preservation.json：确认原I/T/A/bad保持，只增加辅助bad。
  plan.json：cap.plan.v1，原始根目标、证明规则、任务、查询哈希、实际用于
             闭合的证据。失败探索和被回退替代的查询不会算作必需成功任务。
  各检查目录：SMT公式、CIll导入记录、运行命令、日志、证明或反例检查记录。
  result.json：cap.result.v1，最终状态、全部检查、模型调用用量和成本。
  events.jsonl：逐阶段事件；中断时保留已经发生的调用，不假定其费用为零。
  code/：实际执行版本的源码快照；代码在运行中被修改会拒绝接受结果。

对照输出额外包含comparison.json、summary.json和summary.tsv。
父进程和工作进程都不会覆盖旧实验目录。已有目录只有compare --resume
且配置及输入一致时可接续；完成的组不会重新调用API。被中断的组另建
attempt目录，旧记录保留，并标为不能直接作严格耗时对比。

3. 候选的含义

候选格式：{"analysis":"分析说明","lemmas":[EXPR,...]}。
EXPR可为{"ref":节点ID}、{"const":整数,"width":位宽}，或
{"op":"eq","args":[EXPR,EXPR]}。
支持not/ite/and/or/xor/eq/neq/ult/ulte/add/sub，最多12条布尔关系。
引用、运算数量、深度及位宽均检查；不接受模型给出的代码或命令。

候选只变成“额外需要证明的性质”。原始初始化I、转移T、环境A和bad列表
逐项保持不变，原文件字节前缀也保持。模型不能修改时钟、reset、环境或RTL。
当前接口不允许新增历史寄存器，能力小于论文中的完整CIll代理。

结构上下文有固定字节预算。自动扩展原目标的组合依赖和若干层状态更新，
并明确列出未展开边界。缺少更新方程不等于该信号可以任意变化；实际证明
始终使用完整原模型。没有信号名时不会凭空捏造RTL映射。

--context-mode neighborhood为默认片段模式；--context-mode full可显式发送
完整冻结BTOR，保留所有init/next/constraint，模型文件上限640KiB，超过则
拒绝而不截断。完整模式不会自动恢复RTL变量名，也不意味着模型更易理解。
DeepSeek请求体上限768KiB；本地模型传输上限没有随之扩大。

拆分检查的反馈来自最后仍然SAT的义务，不采用已经被完整前提回退证明的
局部失败。多个未闭合义务中，按直接状态位数优先选择涉及更多设计状态的
一个，全部未闭合义务仍保留。观测继续展开一层状态更新依赖，最多64个
状态、每帧8192位，优先保留宽状态；遗漏列表明确记录。这是启发式，不是
已证明的最优选点策略。cti-focused.json保存目标、查询和精确取值，宽值
转成十六进制并保留位宽。发送的反馈最多24000字符，原始求解日志仍保存。

4. 怎么闭合证明

原目标和全部候选的合取是G。拆分器生成C0、C1等子目标及当前拍前提Si：
  检查G与所有Ci的合取等价；
  检查原初始化和环境保证G；
  检查G能够推出实际使用的Si；
  检查Si、原转移和原环境保证下一拍Ci；
  检查原模型存在执行。
局部前提不足时尝试全部当前拍关系，不假设其它下一拍目标已经成立。
只有整组通过才能给出SAFE。单个helper通过不等于原性质通过。

普通rIC3/CIll也检查同一个冻结模型。CIll通过前端缓存接口导入BTOR，
hash.ron只记录真实输入文件哈希，没有导入或伪造任何证明结果。作者二进制
和证明算法不修改；读取前后的dut.btor必须与输入字节一致。
这是原版CIll后端的输入适配，不是执行了作者的RTL前端或完整GPT代理。

SMT的归纳步骤SAT只是CTI，不自动报UNSAFE。UNSAFE必须有从原初始化出发
的见证，并由BtorSim回放成功。见证如果只违反新增helper，返回
CANDIDATE_REJECTED，不会误报原电路有错。
CIll的SAFE是可信后端报告，它当前未导出独立可检查的完整证明证书；
我们的SAFE也仍信任BTOR到SMT翻译器及求解器。各结果保留assurance说明。

5. 两种对照不要混算

end_to_end：从原始问题开始检查；需要时调用模型、编译候选、验收并反馈。
所有阶段、失败候选和API用量都计入结果。模型不给候选或截断会如实停止。
两组使用同一模型、相同源码/图信息和预算，反馈取自各自实际检查器；
我们的组采用结构引导提示及拆分证明，CIll组采用CTI引导提示及原版后端。
这不是只改变一个变量的消融实验，也不等价于论文完整代理。

fixed_candidate：显式提供同一份候选JSON，跳过先解原题，直接比较候选验收。
这组只比较已有关系之后的成本；不能把零次API调用说成自动发现免费。
也可将已有全部目标及候选的冻结模型作为输入，provider=off比较证明后端。
这种问题包的scope必须写明包含现成候选。

方法：split=我们的自动拆分；hybrid=拆分后独立证明剩余关系再组合；
whole=整体SMT消融；cill=原版CIll后端；
plain=普通rIC3。默认单核、16GiB，组间顺序运行；工具参数和线程数全保存。
--seconds为每组总预算，--check-seconds为每次后端上限，--query-seconds
为单个SMT查询/短BMC/CTI上限。--api-seconds为单次API上限，默认1200秒，
可设1至3600秒，并且受剩余总预算限制。--max-tokens默认131072，
可设1至393216；这是推理和最终输出共用的额度，不保证全部用完。
DeepSeek响应字节上限为16MiB，避免长推理被旧2MiB限制截断。
接口依据：https://api-docs.deepseek.com/api/create-chat-completion/（2026-10-29）。
求解/API受硬超时控制；本地解析、哈希等
收尾也计入实测成本，因此总记录可能略超过预算。整机负载不做隔离。
共享prepare成本单列，并提供逐组计入后的总成本，不能只比较最快子目标。

6. 最小复现

在 /home/wudl/circuit-analysis-proof 中：

  make
  ./circuit-analysis-proof --workflow prepare \
    proof_workflow/examples/paired.json --out /tmp/cap-paired-new

  ./circuit-analysis-proof --workflow compare /tmp/cap-paired-new \
    --out /tmp/cap-paired-proof-new --methods split whole cill \
    --provider replay --experiment fixed_candidate \
    --candidate proof_workflow/examples/relation.json \
    --seconds 180 --check-seconds 120 --query-seconds 15

把candidate换成examples/false_relation.json，预期返回CANDIDATE_REJECTED。
这些小样例用于验收框架，不用于宣称工业性能提升。

真实难题，先准备请求指定官方BTOR；包准备好后：
  ./circuit-analysis-proof --workflow compare PACKAGE --out NEW_RUN \
    --methods split cill --provider deepseek --max-rounds 1 \
    --max-tokens 131072 --api-seconds 1200 --reasoning-effort high \
    --seconds 1800 --check-seconds 300 --query-seconds 30

默认provider=off，不调用模型。DeepSeek复用已有持久配置；固定端点，密钥
不进入问题包、模型消息或日志。截断不会自动追加付费请求。
这里指同一组不重试；compare中预先指定的另一对照组仍按自己的预算执行。
例如split/cill各一轮，就是事先限定最多两次请求，不因一组失败追加第三次。

测试：
  make test
  cd proof_workflow
  python3 -B -m unittest test_feedback.py test_context.py test_api_budget.py test_workflow.py

7. 边界

v1支持有明确安全目标的BTOR2位向量模型，以及显式文件清单的RTL前端。
不支持数组sort、进展性质、物理切断后的合同替换、无限制代理代码编辑。
新RTL前端使用Yosys/slang两态采样语义，不额外强制首次reset；它是固定的
编译流程，还不是RTL与BTOR转换正确性的机器证明。
原有--check-input路径仍沿用C++读取器，与这里的研究前端分别记录能力。

本轮测试记录见 RESULTS_20261029_ZH.txt；现有大样例与失败情况均保留。
后续131072-token重试及候选验收见 TOKEN_BUDGET_20261029_ZH.txt。
中间档选题与完整上下文/定向反馈探索见 MIDDLE_TIER_RESEARCH_20261029_ZH.txt。
该轮/tmp原始记录在归档时已无法访问，报告明确标注证据缺口，不作为正式性能数据。

按历史 1800/900 秒梯度筛选并重新测量的实验见 RUNTIME_LADDER_20261029_ZH.txt。
新增独立试验入口 residual_bridge.py：输入已冻结的问题包和已有候选，先做
拆分 SMT；若第一条根义务通过且仅剩一条未闭合义务，就保留原 I/T/A，
对该关系单独做 IC3 可达性证明，再按归纳规则组合。没有把关系直接当假设。
这是 fixed-candidate 验收入口，不调用 API。后续集成版本已经接到
C++ --workflow run --methods hybrid，可在每轮候选产生后自动转交剩余关系。

  python3 -B proof_workflow/residual_bridge.py PACKAGE \
    --candidate CANDIDATE.json --out NEW_DIR --seconds 600 --cpu 28

在 p18 第一轮自动候选上，完整固定候选流程实测 SAFE 约25秒；同一候选
整体交给 IC3/CIll 各300秒超时。原题普通 IC3 约912秒。候选发现成本另算，
不能据此宣称已经实现25秒的自动端到端求解。错误辅助关系不会被上报为
原电路 UNSAFE；test_residual_bridge.py 用可达反例检查了这一边界，并检查
对原初始化、转移和环境的改动会被拒绝。

完整混合流程（新实验，原输入未带入旧候选）：
  ./circuit-analysis-proof --workflow run PACKAGE --out NEW_DIR \
    --methods hybrid --provider deepseek --context-mode full \
    --seconds 1800 --check-seconds 300 --bridge-seconds 600 \
    --max-residuals 4 --max-rounds 2 --api-seconds 900 \
    --max-tokens 131072 --compress-queries

hybrid 复用当前轮已生成的 SMT 义务，不重复执行整套 split。默认最多一个
剩余子句，可显式设 --max-residuals；多个剩余子句作为合取 H 独立证明。
只有已证明 H 在原 I/T/A 下不变，才允许替代这些未闭合归纳步骤。原第一个
根步骤仍未闭合、base/support/coverage 未通过或残余数超限时，不启用转交。
副目标的 UNSAFE 只拒绝候选；不会误报原电路。--bridge-seconds 是每轮独立
证明上限，仍受 --seconds 总预算限制。所有轮次与失败尝试都计入总墙钟。

result.json 的 timing 单列 llm_api_wall_seconds、proof_stage_wall_seconds、
other_wall_seconds，三者之和是 seconds；shared_prepare_seconds 单独列出。
proof_stage 包含残余 IC3 和归档时间。远端模型计算不是本地单核资源的一部分。
plan.json 会将被独立证明替代的原 SAT 步骤标为不用于闭合，并加入实际 side
模型、证书哈希和 SAFE 任务，不会把 SAT 改写成 UNSAT。

--compress-queries 在阶段完成且反馈已提取后，无损压缩 SMT 查询。结果记录
仍保存未压缩查询哈希，compressed-queries.json 提供映射。重放前用 gzip 解压，
再核对 sha256。已完成的 runtime-ladder-20261029 查询也采用了此归档方式，
原始 artifact-manifest.json 继续描述解压后的文件；全部主记录在项目目录。

多样例从零测试见 HYBRID_GENERALIZATION_20261029_ZH.txt；其中明确区分开发
控制题、之前研究过的难题和未参与 LLM 调试的样例，不混称独立测试集。
