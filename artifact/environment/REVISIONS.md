# 实现版本与冻结文件

## Modelchecker

- 基础 Git commit：`1893421256f61d08456ca99349cf6369c6439ab9`
- 工作树有未提交修改；完整 tracked diff：`../code/mc_worktree.patch`
- 关键源码快照：`../code/mc_source_snapshot/`
- selector 使用的冻结可执行文件：`../bin/modelchecker-gauss-auto-v1`
- executable SHA256：`83d12c19856951adc32a1187f6253f45c2cb8cd44969cad4130d752d669bd7d8`

## SAT 后端

- CaDiCaL API/version：1.5.2（仓库内修改版，改动包含在 MC patch/source 中）
- CryptoMiniSat：5.14.5
- `libcryptominisat5.so.5.14` SHA256：
  `ee3be1217a7e0c90d76384d55eeb816fe874cdba0fc093fb3b7f69003e01091a`
- `libcmsat_wrapper.so` SHA256：
  `a2205687080af5fd7089879da287a8eb95b54dfa92d8c2e13d4b1f6948859985`
- wrapper/依赖上层仓库 commit：`ded074538a3a7511d758f5974ab58b573a9e3737`

## rIC3

- stock comparison commit：`7149d568785b039134f0b2baa58358c8af63e70d`
- 当前工作树差异保存在 `../code/ric3_worktree.patch`，但论文 stock 对比不应混用这些
  后续未提交改动。
- artifact 中的 `../bin/cadical-ric3-stock` 来自 stock rIC3 构建，SHA256 为
  `ad9c547047647c99c96f59d445d3d633ca1b56b3450d30455194f63448bffe79`。

冻结 selector 二进制已用于新的 15 点长时限双启动确认。两个 seed 均得到 15/15
严格 Gaussian-only；最终论文应引用
`../data/pathb_crc_gauss_boundary_1800_frozen_v1/`，早期 2026-08-19 结果只作旁证。

## Independent certificate checker

- checker：`../code/check_affine_pdr_certificate.py`，SHA256
  `671a5f3ab802e66198369c6571a2aec696a2980ecaa50438b1e3e6f8347a5eab`；
- checker wrapper：`../bin/certificate/libcmsat_wrapper.so`，SHA256
  `21acabd49b51fb3478613ccf9c13568da11c3c21474835b5e91fcde387391787`；
- checker CryptoMiniSat：`../bin/certificate/libcryptominisat5.so.5.14`，SHA256
  `2d3b8bd0254d653fde985d53dbee33b974e7661e16bcbde0fc31725e69606266`；
- wrapper source：`../code/cmsat_wrapper_certificate.cpp`，SHA256
  `c80d19e751508d6c53f96792565c46de37291fb6f8356eec9d6c67fe8592e764`。
