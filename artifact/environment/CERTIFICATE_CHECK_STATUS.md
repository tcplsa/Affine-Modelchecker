# SAFE 独立检查状态

## 结论

证书阻塞项已经解决。独立 XOR-aware 1-induction checker 对以下模型全部返回
`PASS`：

- 15/15 个 CRC-16/32/64 长时限主边界模型；
- 2/2 个对 stock rIC3-4 的 CRC-32 边界模型。

15 个主模型的逐模型验证时间为 0.16--2.72 秒；两个 rIC3 对比模型分别约为
0.64 秒和 0.46 秒。验证时间独立记录，不计入论文原求解 wall time。

结果位于：

- `data/affine_certificate_validation_v1/core_15/`；
- `data/affine_certificate_validation_v1/ric3_2/`。

## 检查内容

检查器 `code/check_affine_pdr_certificate.py` 不调用 MC 或其 PDR 实现，而是：

1. 独立解析原始 ASCII AAG；
2. 从原 AND 网络重新识别规范的二输入 XOR 模式；
3. 对每个三 AND 的局部 XOR 模式穷举四种输入赋值，排除恢复错误；
4. 将原始 AND-CNF 与已经验证的原生 XOR 等式同时交给 CryptoMiniSat；
5. 检查 `Init => I` 和 `I & T => I'`，其中
   `I = not bad AND exported blocked-cube clauses`。

本批 17 个模型不需要额外 blocked-cube lemma：性质本身均为一步归纳，因此每个
模型只需证明 `Init => not bad` 和 `not bad & T => not bad'`。检查器也支持
`mc-pdr-invariant-v1` 的非空 lemma 文件；回归测试覆盖了“性质单独不归纳，但加入
合法 strengthening lemma 后通过”的情形，并确认初态错误、非归纳性质和缺失
lemma 均会被拒绝。

## 信任边界与准确措辞

CryptoMiniSat 仍属于 verifier 的可信 SAT/XOR 后端，但 verifier 的 AAG 解析、XOR
恢复、时间展开和归纳义务构造均与 MC 的 PDR 流程独立。论文可以写：

> All 17 reported SAFE boundary instances were independently validated by an
> XOR-aware 1-induction checker over the original AAG models.

不要写成“生成了标准 AIGER certificate”。旧 `-certificate` 导出器对 XAG 的确仍会
产生非法 AAG；当前解决方案是独立验证原模型上的归纳证明义务，而不是修复该旧格式。

本次 verifier 冻结文件：

- checker SHA256：`671a5f3ab802e66198369c6571a2aec696a2980ecaa50438b1e3e6f8347a5eab`；
- wrapper SHA256：`21acabd49b51fb3478613ccf9c13568da11c3c21474835b5e91fcde387391787`；
- CryptoMiniSat library SHA256：`2d3b8bd0254d653fde985d53dbee33b974e7661e16bcbde0fc31725e69606266`；
- wrapper source SHA256：`c80d19e751508d6c53f96792565c46de37291fb6f8356eec9d6c67fe8592e764`。

完整 artifact 根目录下可先运行统一核验：

```bash
python3 code/verify_artifact.py
```

单模型复核时，应确保加载 verifier 自己冻结的 CMSat 依赖：

```bash
LD_LIBRARY_PATH="$PWD/bin/certificate" \
python3 code/check_affine_pdr_certificate.py MODEL.aag \
  --cmsat-wrapper bin/certificate/libcmsat_wrapper.so
```
