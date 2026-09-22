# 原始 SAT 查询轨迹已压缩归档

2834 个原始文件保存在 `traces_20260922.tar.gz`。压缩后通过 GNU tar --compare 逐字节对照原文件，再移除展开的 traces 目录。

逐样例表和报告仍在原位置；复跑旧 trace replay 前，在本目录执行：

```bash
sha256sum -c traces_20260922.tar.gz.sha256
tar -xzf traces_20260922.tar.gz
```

这是存储归档，不能据此把原实验解释为无效。轨迹未上传 GitHub，GitHub 保存结果、分析与成员清单；完整归档仍保留在本机。
