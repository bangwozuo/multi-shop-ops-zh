# -*- coding: utf-8 -*-
"""
规格/类目映射维护工作流 —— 端到端编排脚本（与 SKILL.md 的 DAG 一致）。

流程：
  S1 类目属性映射（原子技能 category-attribute-mapping）
      ERP 内部规格类目 → 平台新季度类目库：同名命中为高置信、
      同义词/语义近似为中置信、无对应为不映射
  S2 映射表更新
      与旧映射表逐条对比，产出 变更类型（不变/调整/新增/失效），
      高置信直接生效，中置信标「需人工确认」，不映射标「待建目」

本脚本承担 S1-S2 的确定性部分；建目申请与资质确认措辞由模型按 prompt.txt 完成。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物：
  out/step1_映射结果.json / out/step2_更新明细.json   各步中间产物（每步读上一步产物）
  out/映射表.csv / out/映射表更新.md                  最终交付物
  out/flow_result.json                                机器可读汇总
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(HERE), "out"))

# 同义词规则：(ERP 关键词, 平台类目关键词, 置信度)
SYNONYM_RULES = [
    ("保温杯-不锈钢", "保温杯", "高"),
    ("保温杯-玻璃内胆", "保温杯", "中"),
    ("水杯-塑料", "儿童水杯", "中"),
    ("马克杯-陶瓷", "马克杯", "高"),
    ("小家电-衣物护理", "干衣烘鞋机", "高"),
    ("小家电-厨房料理", "料理机", "中"),
]


def demo_data():
    """来自 runs_v2 实跑输入（平台类目库季度更新，ERP 6 条 → 抖店新类目库 7 条）。"""
    return {
        "source_set": ["ERP-A01 保温杯-不锈钢", "ERP-A02 保温杯-玻璃内胆",
                       "ERP-A03 水杯-塑料", "ERP-A04 马克杯-陶瓷",
                       "ERP-A05 小家电-衣物护理", "ERP-A06 小家电-厨房料理"],
        "target_set": ["餐饮具/水杯/保温杯", "餐饮具/水杯/玻璃杯", "餐饮具/水杯/儿童水杯",
                       "餐饮具/水杯/马克杯", "家用电器/生活电器/干衣烘鞋机",
                       "家用电器/生活电器/料理机及配件", "厨房/烹饪锅具"],
        "old_mapping": {"ERP-A01 保温杯-不锈钢": "餐饮具/水杯/保温杯",
                        "ERP-A04 马克杯-陶瓷": "餐饮具/水杯/马克杯"},
    }


def step1_match(payload, outdir):
    """S1 类目属性映射：同名 → 同义词 → 不映射。"""
    sources = payload.get("source_set") or []
    targets = payload.get("target_set") or []
    if not sources or not targets:
        raise SystemExit("[错误] source_set 与 target_set 均不能为空：缺失让用户补齐，不估算")
    mapping = []
    for src in sources:
        hit = None
        for src_kw, tgt_kw, conf in SYNONYM_RULES:
            if src_kw in src:
                cand = [t for t in targets if tgt_kw in t.split("/")[-1]]
                if cand:
                    hit = (src, sorted(cand, key=len)[0], conf,
                           "同名命中" if conf == "高" else f"同义词「{tgt_kw}」近似命中")
                    break
        if hit is None:
            hit = (src, "（不映射）", "不映射", "无命中规则，目标侧无对应类目")
        mapping.append({"source": hit[0], "target": hit[1],
                        "confidence": hit[2], "basis": hit[3]})
    result = {"mapping": mapping, "count": len(mapping)}
    path = os.path.join(outdir, "step1_映射结果.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result, path


def step2_update(payload, outdir):
    """S2 映射表更新：读 S1 产物，对比旧表产出变更类型。"""
    s1 = json.load(open(os.path.join(outdir, "step1_映射结果.json"), encoding="utf-8"))
    old = payload.get("old_mapping") or {}
    rows = []
    for m in s1["mapping"]:
        src, tgt, conf = m["source"], m["target"], m["confidence"]
        if tgt == "（不映射）":
            change, action = "新增-待建目", "人工确认后申请建目"
        elif conf == "高":
            change = "不变" if old.get(src) == tgt else "调整"
            action = "直接生效"
        else:
            change = "调整" if old.get(src) != tgt else "不变"
            action = "需人工确认后生效"
        rows.append({"source": src, "target": tgt, "confidence": conf,
                     "basis": m["basis"], "change": change, "action": action})
    stats = {"总数": len(rows),
             "直接生效": len([r for r in rows if r["action"] == "直接生效"]),
             "需人工确认": len([r for r in rows if r["action"] == "需人工确认后生效"]),
             "待建目": len([r for r in rows if r["change"] == "新增-待建目"])}
    result = {"rows": rows, "stats": stats}
    path = os.path.join(outdir, "step2_更新明细.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result, path


def write_final(step2, outdir):
    """最终交付物：映射表 CSV + 更新报告 MD。"""
    rows = json.load(open(os.path.join(outdir, "step2_更新明细.json"), encoding="utf-8"))["rows"]
    csv_path = os.path.join(outdir, "映射表.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ERP规格类目", "平台类目", "置信度", "匹配依据", "变更类型", "生效方式"])
        for r in rows:
            w.writerow([r["source"], r["target"], r["confidence"], r["basis"],
                        r["change"], r["action"]])
    lines = ["**AI 生成内容**", "", "# 类目映射表更新报告", "",
             "| ERP规格类目 | 平台类目 | 置信度 | 变更类型 | 生效方式 |",
             "|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['source']} | {r['target']} | {r['confidence']} "
                     f"| {r['change']} | {r['action']} |")
    md_path = os.path.join(outdir, "映射表更新.md")
    open(md_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    return [csv_path, md_path]


def main():
    ap = argparse.ArgumentParser(description="规格/类目映射维护工作流（映射→表更新）")
    ap.add_argument("--input", help="输入 JSON")
    ap.add_argument("--outdir", default=OUT_DEFAULT)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = demo_data() if a.demo else (
        json.load(open(a.input, encoding="utf-8")) if a.input else ap.error("需要 --input 或 --demo"))
    os.makedirs(a.outdir, exist_ok=True)

    s1, p1 = step1_match(payload, a.outdir)
    s2, p2 = step2_update(payload, a.outdir)
    files = write_final(s2, a.outdir)

    result_path = os.path.join(a.outdir, "flow_result.json")
    json.dump({"flow": "spec-category-mapping-flow", "steps": [p1, p2] + files,
               "summary": f"映射 {s2['stats']['总数']} 条：直接生效 {s2['stats']['直接生效']}、"
                          f"需人工确认 {s2['stats']['需人工确认']}、待建目 {s2['stats']['待建目']}",
               "note": "映射与变更类型由本脚本判定；建目申请措辞由模型按 prompt.txt 完成"},
              open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"工作流完成 —— 映射 {s2['stats']['总数']} 条，"
          f"需人工确认 {s2['stats']['需人工确认']} 条，待建目 {s2['stats']['待建目']} 条")
    for f in [p1, p2] + files + [result_path]:
        print(" 产物:", f)


if __name__ == "__main__":
    main()
