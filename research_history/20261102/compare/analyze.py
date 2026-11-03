#!/usr/bin/env python3
"""
分析 compare.tsv，输出统计报告。
聚焦: 1) blif(PIC3) 比 mc 快多少
      2) 超时统计
      3) mismatch 统计
"""

from pathlib import Path

TSV = Path(__file__).resolve().parent / "results" / "compare.tsv"
CSV_CLEAN = Path(__file__).resolve().parent / "results" / "compare_clean.csv"
REPORT = Path(__file__).resolve().parent / "results" / "report.txt"

# ---- Step 1: 从 TSV 清理并输出 CSV ----
def clean_tsv():
    lines = TSV.read_text().splitlines()
    cleaned = []
    for line in lines:
        if not line.strip():
            continue
        cols = line.split("\t")
        if cols[0] == "name":
            # 新表头: name, pic3_status, pic3_time, mc_status, mc_time, match, note
            cleaned.append(",".join([cols[0], cols[2], cols[3], cols[4], cols[5], cols[10], cols[11]]))
        else:
            if len(cols) < 12:
                continue
            cleaned.append(",".join([cols[0], cols[2], cols[3], cols[4], cols[5], cols[10], cols[11]]))
    CSV_CLEAN.write_text("\n".join(cleaned) + "\n")
    print(f"清理后的 CSV 写入: {CSV_CLEAN}")
    return cleaned


# ---- Step 2: 分析 ----
def analyze():
    raw = TSV.read_text().splitlines()
    total = 0
    safe_both = 0
    unsafe_both = 0
    timeout_both = 0
    mismatch_cases = []
    blif_faster = 0       # blif 比 mc 快（两者都成功时）
    mc_faster = 0         # mc 比 blif 快
    blif_timeout = 0
    mc_timeout = 0
    both_timeout = 0
    mc_error = 0
    blif_error = 0
    blif_faster_pairs = []  # 记录 blif 更快的具体数据
    mc_faster_pairs = []
    mismatch_blif_safe_mc_unsafe = []
    mismatch_blif_unsafe_mc_safe = []
    both_timeout_match_ok = 0  # 双方超时但 match 列为 OK

    for line in raw:
        if line.startswith("name\t"):
            continue
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 12:
            continue
        name = cols[0]
        ps = cols[2]   # pic3_status
        pt_str = cols[3]  # pic3_time
        ms = cols[4]   # mc_status
        mt_str = cols[5]  # mc_time
        match = cols[10]  # match
        note = cols[11] if len(cols) > 11 else ""

        total += 1

        # 解析时间
        try:
            pt = float(pt_str) if pt_str else None
        except ValueError:
            pt = None
        try:
            mt = float(mt_str) if mt_str else None
        except ValueError:
            mt = None

        # 超时统计（MC ERROR 视作超时）
        if ps == "TIMEOUT":
            blif_timeout += 1
        if ms == "TIMEOUT" or ms == "ERROR":
            mc_timeout += 1
        if ms == "ERROR":
            mc_error += 1
        if ps == "ERROR":
            blif_error += 1
        if ps == "TIMEOUT" and ms in ("TIMEOUT", "ERROR"):
            both_timeout += 1

        # match 分类
        if match == "OK":
            if ps == "SAFE" and ms == "SAFE":
                safe_both += 1
            elif ps == "UNSAFE" and ms == "UNSAFE":
                unsafe_both += 1
            elif ps == "TIMEOUT" and ms == "TIMEOUT":
                both_timeout_match_ok += 1
            # 速度比较：仅两者都非 TIMEOUT/ERROR 时才比较
            if ps in ("SAFE", "UNSAFE") and ms in ("SAFE", "UNSAFE"):
                if pt is not None and mt is not None and pt > 0 and mt > 0:
                    if pt < mt:
                        blif_faster += 1
                        blif_faster_pairs.append((name, pt, mt, mt-pt))
                    else:
                        mc_faster += 1
                        mc_faster_pairs.append((name, pt, mt, pt-mt))
        elif match == "MISMATCH":
            mismatch_cases.append((name, ps, ms, note))
            if ps == "SAFE" and ms == "UNSAFE":
                mismatch_blif_safe_mc_unsafe.append((name, pt, mt))
            elif ps == "UNSAFE" and ms == "SAFE":
                mismatch_blif_unsafe_mc_safe.append((name, pt, mt))
        elif match == "TIMEOUT":
            pass  # 已统计

    # ---- 生成报告 ----
    report_lines = []
    def w(s=""):
        report_lines.append(s)

    w("=" * 60)
    w("PIC3 (BLIF) vs Modelchecker-xag (AIG) 对拍结果统计报告")
    w("=" * 60)
    w()
    w(f"总计测试用例: {total}")
    w()

    # -- 一、结果一致性 --
    w("一、结果一致性")
    w()
    ok_count = safe_both + unsafe_both + both_timeout_match_ok
    w(f"  两者结果一致 (OK): {ok_count} 个")
    w(f"    - 均为 SAFE:     {safe_both} 个")
    w(f"    - 均为 UNSAFE:   {unsafe_both} 个")
    w(f"    - 均为 TIMEOUT:  {both_timeout_match_ok} 个")
    w(f"  一方超时另一方有结果 (match=TIMEOUT): {blif_timeout - both_timeout} 个")
    w(f"  结果不一致 (MISMATCH): {len(mismatch_cases)} 个")
    w()

    # -- 二、超时分析 --
    w("二、超时分析")
    w()
    w(f"  PIC3 (BLIF) 超时: {blif_timeout} 个 ({blif_timeout/total*100:.1f}%)")
    w(f"  MC   (AIG)  超时: {mc_timeout} 个 (含 ERROR {mc_error}个) ({mc_timeout/total*100:.1f}%)")
    w(f"  双方均超时/报错:    {both_timeout} 个")
    w(f"  仅 PIC3 超时:       {blif_timeout - both_timeout} 个")
    w(f"  仅 MC 超时/报错:    {mc_timeout - both_timeout} 个")
    w(f"  其中 MC 报错 (ERROR): {mc_error} 个")
    w(f"  PIC3 报错 (ERROR):  {blif_error} 个")
    w()

    # -- 三、速度对比 --
    w("三、速度对比（仅在两者均返回有效结果时比较）")
    w()
    w("  注意：PIC3 为 Python 实现，MC 为 C++ 实现，直接比速度 MC 占优是预期内的。")
    w("  这里重点列出 PIC3 反而更快的案例。")
    w()
    both_valid = blif_faster + mc_faster
    w(f"  可比样本数: {both_valid} 个")
    w(f"  PIC3 更快:  {blif_faster} 个 ({blif_faster/both_valid*100:.1f}%)" if both_valid else "  PIC3 更快: 0")
    w(f"  MC 更快:    {mc_faster} 个 ({mc_faster/both_valid*100:.1f}%)" if both_valid else "  MC 更快: 0")
    w()

    if blif_faster_pairs:
        blif_faster_pairs.sort(key=lambda x: x[3], reverse=True)
        w("  PIC3 更快的全部案例 (按 MC耗时-PIC3耗时 降序):")
        for name, pt, mt, diff in blif_faster_pairs:
            ratio = mt / pt if pt > 0 else 0
            w(f"    {name:<30s}  PIC3={pt:.1f}s  MC={mt:.1f}s  Δ={diff:.1f}s  MC/PIC3={ratio:.1f}x")
    w()

    # -- 四、MISMATCH 详细 --
    w("四、MISMATCH 详情")
    w()
    w(f"  PIC3=SAFE   MC=UNSAFE: {len(mismatch_blif_safe_mc_unsafe)} 个")
    for name, pt, mt in mismatch_blif_safe_mc_unsafe:
        w(f"    {name}")
    w(f"  PIC3=UNSAFE MC=SAFE:   {len(mismatch_blif_unsafe_mc_safe)} 个")
    for name, pt, mt in mismatch_blif_unsafe_mc_safe:
        w(f"    {name}")
    w()

    # -- 五、仅一方超时的案例 --
    w("五、仅一方超时但另一方有结果的案例")
    w()
    only_pic3_timeout = []
    only_mc_timeout = []
    for line in raw:
        if line.startswith("name\t"):
            continue
        if not line.strip():
            continue
        cols = line.split("\t")
        if len(cols) < 12:
            continue
        name = cols[0]
        ps = cols[2]
        ms = cols[4]
        if ps == "TIMEOUT" and ms not in ("TIMEOUT", "SKIPPED", "ERROR"):
            only_pic3_timeout.append((name, ms))
        if ms in ("TIMEOUT", "ERROR") and ps not in ("TIMEOUT", "SKIPPED", "ERROR"):
            only_mc_timeout.append((name, ps))

    w(f"  PIC3 超时但 MC 有结果: {len(only_pic3_timeout)} 个")
    for name, ms in only_pic3_timeout:
        w(f"    {name}  -> MC={ms}")
    w(f"  MC 超时/报错但 PIC3 有结果:   {len(only_mc_timeout)} 个")
    for name, ps in only_mc_timeout:
        w(f"    {name}  -> PIC3={ps}")
    w()

    # -- 六、汇总 --
    w("六、汇总")
    w()
    w(f"  总用例数:              {total}")
    w(f"  均 SAFE:               {safe_both}")
    w(f"  均 UNSAFE:             {unsafe_both}")
    w(f"  均 TIMEOUT/ERROR:      {both_timeout_match_ok}")
    w(f"  PIC3 超时但 MC 有结果: {blif_timeout - both_timeout_match_ok}")
    w(f"  MC 超时但 PIC3 有结果: {mc_timeout - both_timeout_match_ok}")
    w(f"  MISMATCH:              {len(mismatch_cases)}")
    w(f"  MC ERROR (计入超时):   {mc_error}")
    w(f"  BLIF 更快:             {blif_faster}")
    w(f"  MC 更快:               {mc_faster}")

    report = "\n".join(report_lines)
    REPORT.write_text(report)
    print(report)
    return report


if __name__ == "__main__":
    clean_tsv()
    analyze()
