# Affine-PDR 论文数据包

本目录保存 `main.pdf` 当前初稿所引用的实验数据、输入模型、分析脚本和实现快照。
原始结果均从 `test_tools/compare/results` 原样复制；没有为了匹配论文而修改 TSV、
JSON 或日志。

## 论文主张与数据位置

| 论文内容 | 主要原始数据 |
| --- | --- |
| 180 秒粗粒度 CRC 边界、15 个 Gaussian-only 点 | `data/pathb_crc_gauss_boundary_v1/gauss_180.tsv` |
| CRC-16/32/64 精细边界 | `data/pathb_crc_gauss_boundary_fine_v1/gauss_180.tsv` |
| 15 个点的冻结二进制 1,800 秒、双启动、纯四 lane 确认 | `data/pathb_crc_gauss_boundary_1800_frozen_v1/` |
| 早期长时限一致性旁证 | `data/pathb_crc_gauss_boundary_1800_confirm_v1/` |
| 两个 CRC-32 对 stock rIC3-4 的 1,800 秒确认 | `data/pathb_real_xor_apps_v1/crc32_gauss_1800_confirmation.md` 及对应 TSV/JSON |
| 17 个 SAFE 边界模型的独立归纳检查 | `data/affine_certificate_validation_v1/` |
| 深层 residue 负对照 | `data/pathb_crc_residue_backend_diag_v1/`、`data/pathb_crc_frame_residue_v1/` 和 `data/pathb_affine_dynamic_gate_crc_v1` |
| XOR island 正确性与 CRC32C 五次运行 | `data/xor_island_compression_v1/` |
| 387 模型 selector、256/131 冻结划分和 27 个阈值 | `data/pathb_affine_selector_validation_v1/` |
| selector 所需生成 AIGER | `data/selector_benchmarks/` |
| 12 个公开 RTL 的来源、转换产物和日志 | `data/pathb_public_affine_rtl_v1/` |

`reports/` 是解释性材料，不替代上述原始数据。`code/pathb/` 保存生成器、运行器和
分析脚本；项目根目录保存当前实现，`third_party/` 保存 CryptoMiniSat 接口扩展。
`environment/` 记录版本和机器信息。冻结二进制未纳入 Git 仓库，其哈希保留用于
标识产生原始数据的版本。

selector 原始 manifest 保持不变以保存证据；可移植副本为
`data/pathb_affine_selector_validation_v1/manifest.relative.json`，其中 387 个输入
已逐一通过 SHA256 校验。

冻结二进制的 15 点双启动重跑已经完成，二进制 SHA256 为
`83d12c19856951adc32a1187f6253f45c2cb8cd44969cad4130d752d669bd7d8`。
两个 seed 均得到 15/15 严格 Gaussian-only，详情见该目录的 `report.md`。

## 可直接复核的关键结果

1. 两个冻结 1,800 秒 TSV 各有 15 行，三元状态均为
   `CaDiCaL=TIMEOUT, CMSat-no-Gauss=TIMEOUT, CMSat-Gauss=SAFE`；每个配置的
   `portfolio_lanes` 为 4。
2. 独立 XOR-aware checker 在原始 AAG 上验证了 15/15 个主模型和 2/2 个 rIC3
   对比模型；逐模型 AAG SHA256、义务统计和时间见 certificate 目录。
3. selector 默认策略 `(32, 0.75, 2)` 在 holdout 上由 74/131 增至 122/131，
   新增 48、丢失 0；原始分析见 selector 目录的 `report.md`。
4. 重新按 16 个 `structure_group` 做 cluster bootstrap 后，holdout 共同可解模型
   的几何均值比仍为 0.677276，但 95% CI 为 `[0.348763, 1.055654]`。复核命令：

```bash
python3 code/group_bootstrap_selector.py \
  data/pathb_affine_selector_validation_v1/oracle_120s.tsv
```

因此 selector 的“+48 且不丢解”是当前更强的证据；运行时比率的组级区间跨 1，
不应继续使用模型独立 bootstrap 的窄区间作确认性结论。

## 已知注意事项

- `pathb_crc_gauss_boundary_v1/gauss_180_report.md` 的标题误写成 120 秒；其 TSV
  中 `timeout_seconds` 全部为 180，论文中的 180 秒口径正确。
- `pathb_crc_gauss_boundary_fine_1800_confirm_v1/seed986011.tsv` 只有表头，没有
  实验行，不能用于任何 1,800 秒主张。
- 原始 manifest 保留运行机器上的绝对路径以保存原始证据；可移植实验使用已生成
  并校验的 `manifest.relative.json`。
- 数据记录了随机种子和运行状态，但早期长时限 TSV 没有记录可执行文件 SHA256。
  详见 `KNOWN_DATA_GAPS.md`。

## 完整性

`SHA256SUMS` 覆盖本 artifact 中除自身之外的全部稳定文件，包括已完成的 frozen
rerun。

```bash
find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
```
