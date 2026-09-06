# 论文实验环境（作者确认 + runner 核验）

- 所有论文实验服务器硬件配置一致，采用 AMD EPYC 7763 64-Core Processor；
  2 sockets，64 cores/socket，1 hardware thread/core。
- 每台机器内存 1.0 TiB，操作系统为 Ubuntu 20.04.4 LTS，kernel 5.4.0-204。
- 实验期间机器由本项目独占，没有其他用户计算任务并行运行。
- runner 没有使用 `taskset` 或显式 NUMA 绑定，由 Linux 调度器分配核心；没有记录
  关闭动态频率或固定 CPU 频率的操作。
- 项目没有设置额外的逐进程内存上限；论文实验中未发生 OOM、swap 压力导致的
  失败或系统因内存终止进程。
- GCC/G++ 13.1.0；Rust/Cargo 1.96.0；CMake 4.3.4。

## 计时口径

`compare_runner.py` 在 `subprocess.Popen` 启动整个求解器进程之前读取
`time.monotonic()`，并在进程退出或被 timeout 终止后记录差值。因此每个配置的
`wall_seconds` 包含模型加载、AIG→XAG 转换、仿射/XOR 分析、启用时的 mismatch
validation、SAT 后端初始化以及完整 PDR 求解。runner 的 manifest 构建和不同配置
之间的调度不计入单配置 `wall_seconds`。

论文原实验没有启用最终 certificate checker，因此证书导出和独立重验时间不在
已报告 wall time 中。补充的 XOR-aware 独立检查已单独计时，不回填到原求解时间；
协议与结果见 `CERTIFICATE_CHECK_STATUS.md`。
