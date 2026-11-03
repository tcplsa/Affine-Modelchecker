网表切分研究（当前为会话内研究）
====================

2026-10-24最新状态
  用户已取消定时/后台研究。cron标记段已移除，config.enabled=false；
  当前由本会话直接研究，以下定时说明仅留作配置参考，不代表任务在运行。
  最新成果将汇总在RESEARCH_RESULTS_20261024_ZH.txt和PROGRESS_ZH.txt。

旧调度配置：每小时整点，表达式0 * * * *；当前未安装。
这是服务器本地任务，不会出现在 ChatGPT 的 Scheduled 列表里。
服务器必须开机、cron必须运行；不要求IDE或当前聊天保持打开。
实际安装状态见 cron-installation.json；未生成该回执时不能视为已安装。

持续研究模式（config.json的mode=research_agent）：
  每轮启动一个Codex研究会话，接续PROGRESS_ZH.txt和QUESTIONS.json，
  选择尚未解决的问题，查阅论文/官方实现，设计并运行小实验，记录新证据。
  任务说明见RESEARCH_TASK_ZH.txt；一轮完成后下一小时继续，不以五步结束。
  Codex主研究代理使用现有ChatGPT登录和Codex额度；Qwen作为本地助手，
  复杂咨询再尝试已配置的API。独立API仍需要自己的接口、模型名和密钥。
  每轮约13分钟，外层总上限15分钟，flock防止本任务重叠。

外部代理授权
  自动审批要求用户明确允许研究代理将项目研究上下文发送到ChatGPT/Codex。
  research.external_agent_approved=false时，定时触发仅记录
  AWAITING_EXTERNAL_AGENT_APPROVAL，启动联网代理之前返回。
  只有用户明确授权后才启用；认证文件及密钥不能作为研究资料读取/发送。
  启用后CLI基础设施故障会留存日志，下个整点重试；具体研究问题被阻塞时，
  代理应转向其他可推进问题，不重复输出相同总结。

已有可复用实验（旧config.json tasks，仅供研究代理按需调用）：
  conversion       小型SV转Yosys网表、AIG/AAG，验证正常版本和两个负对照。
  partition        本地Qwen提出节点分区；固定程序物理切分并检查重连等价。
  bridges          检查桥接的正负对照、可达性以及自由割线造成的伪反例。
  cv32_conversion  冻结版本CV32E40X popcnt转AIG，检查AIG序列化往返等价。
  interface_draft  根据实测凭据，提出支持AIG/SAT与BTOR/SMT的接口草案。

旧run_once.py仍可手动推进这些实验，旧state.json保留预检证据。
持续研究的主入口已切换为research_agent.py，不受旧队列完成状态限制。
研究原型写在本目录experiments/，核心实现采用易读C++98风格；
主程序的集成变更先留下可审查原型，正式验证模型及旧结果作为参考。

运行和管理（从项目根目录）：
  ./netlist_research/run.sh --status       查看研究代理状态，不调用模型
  ./netlist_research/run.sh                手动启动一轮持续研究
  ./netlist_research/run.sh --retry        修好基础设施阻塞后立即重试
  python3 netlist_research/install_schedule.py show
  python3 netlist_research/install_schedule.py remove

暂停：把config.json的enabled改为false；重新启用改为true。
改时间：hourly模式修改minute；daily模式修改daily_time；然后install。
安装器只修改标记为本项目的cron段，保留其他用户任务；不会调用sudo。
当前安装器要求主机时区UTC+08:00，避免把命令里的TZ误当成cron调度时区。

本地咨询工具consult_model.py沿用有界适配器，最多两次Qwen和一次API；
回答标为UNVERIFIED_MODEL_ADVICE，需要研究代理查证，不自动当作证明。
API默认留空，没有配置时记录NEEDS_CONFIG。标准Codex登录仅供主研究会话，
不能充当DeepSeek或其他独立API的密钥。network.json保存本机既有无凭据
代理，供cron联网；代理不可达时需要修复连接。该文件不纳入版本管理。

API配置
  修改config.json中api的endpoint、model、key_env或key_file。
  endpoint使用提供商的HTTPS chat/completions地址，model填写确认过的模型ID。
  手工运行可从DEEPSEEK_API_KEY（或key_env指定的变量）读取。
  cron不会继承你在终端export的变量；后台任务可指定绝对路径key_file，
  例如/home/wudl/.config/circuit-analysis-proof/api.key，文件只存密钥一行，
  属主必须是当前用户，权限600。不要把密钥写入项目JSON或cron命令。
  程序只在真正升级API时读取明确指定的密钥文件，不扫描shell配置或认证文件。
  同一用户权限下的其他程序仍可能读取该文件，文件权限不等于密钥隔离。
  本轮只测试了缺配置时不发请求和模拟API后备；真实付费API尚未实测。

产物
  PROGRESS_ZH.txt     当前研究结论、具体缺口与下一步。
  QUESTIONS.json      持续更新的未解决研究问题。
  RESEARCH_LOG_ZH.txt 逐轮研究记录，引用来源和实验产物。
  LATEST_REPORT_ZH.txt 最新一轮代理的简短报告（成功后生成）。
  research_state.json 主研究会话的运行状态。
  research_runs/      每轮任务上下文、事件流、stderr、report和运行回执。
  state.json          旧固定实验队列的预检证据。
  scheduler.log       cron轮次的简短日志。
  runs/<轮次>/        不覆盖的请求、模型回答、提案、工具日志、检查结果。
  partition_manifest.json  子网表、共享PI、跨区端口、极性及同周期桥接映射。
  interface_candidate.json  模型提出的接口草案，仍需技术审查。

当前边界
  partition.py只支持canonical ASCII AAG，最多12个PI+状态位、512个AND。
  B/C必须保留，justice/fairness明确不支持；不会把普通O自动当bad。
  重连等价只证明切分/恢复保持原转移系统，不能代替模块合同的组合证明。
  下一步重点是边界不变量、assume/guarantee义务、时序反馈与循环依赖，
  再在真实顺序模块上比较完整求解和组合求解的结果与耗时。
  整核结果仍为UNKNOWN；本轮没有宣称拆分带来性能收益。

2026-10-24首次预检
  conversion：三个对照符合预期，两个UNSAFE见证均独立回放VALID。
  partition：Qwen最初两次输出对象/错误ID，被拒绝；明确只输出整数ID后，
             新一轮首个候选通过。实际切分2区、5桥，32初态赋值与256步赋值等价。
  bridges：精确重连与原始模型都SAFE；删桥、错源、反相桥被拒绝。
           这个分区自由cut后超过12位穷举上限，明确UNKNOWN；另一个固定微型
           演示的自由cut反例为SPURIOUS，不能混成这个分区的实测反例。
  cv32_conversion预检：popcnt有32输入、6普通输出、197个AND；AIG往返等价。
           比较边界是综合后的bit网表与AIG重新导入，不能据此声称独立证明了
           从原始RTL到bit网表的综合正确性，也没有把6个输出当成6条性质。
  状态、成功和拒绝的模型回答及所有工具结果均保留于runs/。
  上述预检付费API调用次数为0；切换后主研究代理使用Codex CLI及其额度。

小网表基线实验
--------------

fixture.sv 只有两个状态位。left 保存逻辑值，right 保存其反码。
enable=1 时二者采样同一个可变化的 data；enable=0 时保持。
性质是每个时钟采样点 left == !right。
环境约束 enable || !data：暂停时 data=0，更新时 data 可为0或1。
约束是输入合同，不是已经证明的结论。

实验有三个版本：
  good      初态一致，更新规则一致，期望 SAFE。
  bad_init  仅破坏 right 初值，期望 UNSAFE。
  bad_wire  仅把 right 更新接成 data，期望 UNSAFE。
两个负对照都要求独立回放见证有效，检查每步约束和 bad。
因此能够检查初始化是否生效、是否确实允许更新，以及性质是否被假设屏蔽。
SAFE 采用 rIC3 的无界安全结果；本实验不检查 SAFE 证明证书。

从项目根运行（输出目录必须不存在）：
  python3 netlist_research/baseline.py --out /tmp/cap-netlist-baseline-01

可选参数：
  --timeout 30       全部命令的总时间预算，允许1至120秒。
  --yosys 路径       默认 /home/wudl/tools/yosys-0.40/yosys
  --ric3 路径        默认 /home/wudl/rIC3-stock-7149d56/target/release/ric3
退出码0表示三个预期结果和反例回放全部通过；2表示失败或未完成。

每个版本生成：
  model.json        Yosys降位前的网表，包含寄存器、init、$assert、$assume。
  model.aig         二进制 AIGER 1.9，安全输出B和约束C保留。
  model.aag         同一电路的ASCII形式，便于后续读取和分割。
  model.map         Yosys输入、锁存器等符号映射；不是任意RTL结构复原保证。
  build.ys/log      实际转换命令和日志。
  solver.log        rIC3结果及负对照见证。
  replay.json       负对照的独立AAG回放结果。
顶层 result.json 记录状态、工具版本/SHA、输入SHA、AIG统计、命令和结果。
脚本、fixture及现有 verification/lsu/replay_aag.py 会复制到输出目录留档。
现有正式验证模型和配置不会修改。

规模限制：fixture不超过64 KiB，AIG不超过2 MiB，输入与锁存器合计不超过12。
每次构建最多10秒、求解5秒、回放5秒，同时受总预算限制。
不把未定义信号设为零；只把未驱动值保留为anyseq。
Python仅用于这个实验，后续主工具仍可使用易读的C++98实现。
