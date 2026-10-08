# -*- coding: utf-8 -*-
"""
类目属性映射 —— 确定性匹配 + 置信度分级 + 产物生成。

职责边界（重要）：
  本脚本只做**确定性计算与产物生成**：同义词规则命中、字符二元组相似度兜底、
  置信度分级（高/中/不映射）、未匹配双向盘点、CSV/JSON/MD 落盘。
  需要业务语境判断的「需人工确认」项解释、建目建议措辞，由模型按 prompt.txt 完成。

匹配规则（与 prompt.txt 一致）：
  R1 同义词规则  内置同义词表逐条命中，输出 高/中 置信度与匹配依据
  R2 相似度兜底  源条目 × 目标叶子类目做字符二元组（bigram）重叠打分
                 score ≥ 0.8 → 高；0.5 ≤ score < 0.8 → 中；否则不映射
  R3 双向盘点    源侧未命中与目标侧未被覆盖的条目都进入「未匹配项」
  R4 建议        未匹配项按目标侧近似度给出建目/保留建议

用法：
  python match_map.py --input input.json --outdir out
  python match_map.py --demo --outdir out

产物：
  out/映射表.csv       逐条映射（源条目/目标条目/匹配依据/置信度）
  out/映射报告.md      人类可读报告（映射表 + 未匹配项 + 处理建议）
  out/mapping.json     机器可读结果（供工作流/下游技能读取）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(HERE), "out"))

# ---------------------------------------------------------------- 同义词规则（R1）
# (源条目关键词, 目标叶子类目关键词, 置信度, 匹配依据)
SYNONYM_RULES = [
    ("保温杯", "保温杯", "高", "名称完全一致，品类语义相同"),
    ("玻璃水杯", "玻璃杯", "高", "材质（玻璃）与品类（水杯）一一对应"),
    ("马克杯", "马克杯", "高", "马克杯为同一品类词"),
    ("吸管杯", "儿童水杯", "中", "吸管杯与儿童水杯用途重合，需人工确认儿童用品资质"),
    ("挂烫机", "挂烫机", "高", "目标类目明确包含配件"),
    ("烘鞋", "烘鞋机", "中", "干衣与烘鞋同属衣物护理电器，语义接近"),
    ("榨汁", "料理机", "低", "无同名类目，仅功能相近"),
]

HIGH_T, MID_T = 0.8, 0.5  # R2 相似度阈值


def demo_data():
    """来自 runs_v2 实跑输入（淘宝在售 7 条 → 抖店类目库 8 条）。"""
    return {
        "source_set": [
            "保温杯", "玻璃水杯", "陶瓷马克杯", "塑料吸管杯",
            "便携榨汁杯", "挂烫机配件（蒸汽喷头）", "家用烘鞋器",
        ],
        "target_set": [
            "厨房/烹饪锅具", "餐饮具/水杯/保温杯", "餐饮具/水杯/玻璃杯",
            "餐饮具/水杯/马克杯", "餐饮具/水杯/儿童水杯",
            "家用电器/生活电器/挂烫机及配件", "家用电器/生活电器/干衣烘鞋机",
            "个护/口腔护理/电动牙刷",
        ],
    }


# ---------------------------------------------------------------- 相似度（R2）

def bigrams(s: str):
    s = "".join(ch for ch in s if ch.strip())
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}


def similarity(a: str, b: str) -> float:
    ga, gb = bigrams(a), bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))


def leaf(target: str) -> str:
    return target.split("/")[-1]


# ---------------------------------------------------------------- 匹配主流程

def match(payload):
    sources = payload.get("source_set") or []
    targets = payload.get("target_set") or []
    if isinstance(sources, str):
        sources = [x for x in __import__("re").split(r"[;；\n]", sources) if x.strip()]
    if isinstance(targets, str):
        targets = [x for x in __import__("re").split(r"[;；\n]", targets) if x.strip()]
    if not sources or not targets:
        raise SystemExit("[错误] source_set 与 target_set 均不能为空：缺失清单请让用户补齐，不估算")

    mapping, used_targets = [], set()
    for src in sources:
        hit = None
        # R1 同义词规则优先
        for kw, tleaf, conf, basis in SYNONYM_RULES:
            if kw in src:
                cand = [t for t in targets if tleaf in leaf(t)]
                if cand:
                    tgt = sorted(cand, key=len)[0]
                    hit = (src, tgt, basis, conf)
                    break
        # R2 bigram 相似度兜底
        if hit is None:
            best_t, best_s = None, 0.0
            for t in targets:
                s = similarity(src, leaf(t))
                if s > best_s:
                    best_t, best_s = t, s
            if best_t is not None and best_s >= MID_T:
                conf = "高" if best_s >= HIGH_T else "中"
                hit = (src, best_t, f"字符二元组相似度 {best_s:.2f}", conf)
        if hit:
            mapping.append({"源条目": hit[0], "目标条目": hit[1],
                            "匹配依据": hit[2], "置信度": hit[3]})
            if hit[3] in ("高", "中"):
                used_targets.add(hit[1])
        else:
            mapping.append({"源条目": src, "目标条目": "（不映射）",
                            "匹配依据": "无命中规则且相似度低于 0.5", "置信度": "不映射"})

    # R3 双向盘点
    unmatched_src = [m["源条目"] for m in mapping if m["置信度"] == "不映射"]
    unmatched_tgt = [t for t in targets if t not in used_targets]

    # R4 建议
    suggestions = []
    for s in unmatched_src:
        near = max(targets, key=lambda t: similarity(s, leaf(t)))
        suggestions.append(
            f"{s}：目标侧最接近「{near}」（相似度 {similarity(s, leaf(near)):.2f}），"
            f"建议人工确认后建目或放弃映射")
    for t in unmatched_tgt:
        suggestions.append(f"目标类目「{t}」源侧无对应商品，保留在类目库不动")

    stats = {
        "源条目数": len(sources), "目标类目数": len(targets),
        "已映射条数": len([m for m in mapping if m["置信度"] != "不映射"]),
        "高置信条数": len([m for m in mapping if m["置信度"] == "高"]),
        "中置信条数": len([m for m in mapping if m["置信度"] == "中"]),
        "不映射条数": len(unmatched_src), "目标侧未覆盖数": len(unmatched_tgt),
    }
    return mapping, unmatched_src + unmatched_tgt, suggestions, stats


# ---------------------------------------------------------------- 输出层

def write_outputs(mapping, unmatched, suggestions, stats, outdir):
    os.makedirs(outdir, exist_ok=True)
    files = []

    csv_path = os.path.join(outdir, "映射表.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["源条目", "目标条目", "匹配依据", "置信度"])
        for m in mapping:
            w.writerow([m["源条目"], m["目标条目"], m["匹配依据"], m["置信度"]])
    files.append(csv_path)

    md = ["**AI 生成内容**", "", "## 映射结果", "",
          "| 源条目 | 目标条目 | 匹配依据 | 置信度 |", "|---|---|---|---|"]
    for m in mapping:
        md.append(f"| {m['源条目']} | {m['目标条目']} | {m['匹配依据']} | {m['置信度']} |")
    md += ["", "## 未匹配项", ""]
    md += [f"{i}. {u}" for i, u in enumerate(unmatched, 1)] or ["（无）"]
    md += ["", "## 处理建议", ""]
    md += [f"{i}. {s}" for i, s in enumerate(suggestions, 1)] or ["（无）"]
    md_path = os.path.join(outdir, "映射报告.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    files.append(md_path)

    js_path = os.path.join(outdir, "mapping.json")
    with open(js_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "mapping": mapping, "unmatched": unmatched,
                   "suggestions": suggestions,
                   "note": "映射由本脚本确定性判定；建目与资质确认由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(js_path)
    return files


def main():
    ap = argparse.ArgumentParser(description="类目属性映射（同义词规则 + bigram 兜底）")
    ap.add_argument("--input", help="输入 JSON（source_set/target_set）")
    ap.add_argument("--outdir", default=OUT_DEFAULT)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = demo_data() if a.demo else (
        json.load(open(a.input, encoding="utf-8")) if a.input else ap.error("需要 --input 或 --demo"))

    mapping, unmatched, suggestions, stats = match(payload)
    files = write_outputs(mapping, unmatched, suggestions, stats, a.outdir)
    print(f"映射完成 —— 源 {stats['源条目数']} 条：高置信 {stats['高置信条数']}、"
          f"中置信 {stats['中置信条数']}、不映射 {stats['不映射条数']}；"
          f"目标侧未覆盖 {stats['目标侧未覆盖数']} 条")
    for f in files:
        print(" 产物:", f, f"({os.path.getsize(f) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
