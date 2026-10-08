# -*- coding: utf-8 -*-
"""
一稿多平台 Listing 生成工作流 —— 端到端编排脚本（与 SKILL.md 的 DAG 一致）。

流程：
  S1 类目属性映射（原子技能 category-attribute-mapping）
      源类目（淘宝类目库）→ 各平台类目库逐条映射，同名/同义词命中为高置信
  S2 标题多平台改写（原子技能 title-multiplatform-rewrite）
      按 平台字数上限（淘宝 30 / 抖店 30 / 拼多多 60 / 小红书 20）
      与主关键词前 13 字规则生成标题，并做极限词扫描
  S3 上架草稿汇总
      平台 × 类目 × 标题 × 卖点 拼装成上架草稿清单

本脚本承担 S1-S3 的确定性部分；卖点措辞润色与平台差异表达由模型按 prompt.txt 完成。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物：
  out/step1_类目映射.json / out/step2_标题改写.json   各步中间产物（每步读上一步产物）
  out/类目映射表.csv / out/上架草稿.md                最终交付物
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

PLATFORM_LIMIT = {"淘宝": 30, "抖店": 30, "拼多多": 60, "小红书": 20}
TITLE_TEMPLATE = {
    "淘宝": "{brand}{core}{spec}大容量{kw}真空便携",
    "抖店": "{brand}{core}{spec}｜316不锈钢内胆办公便携",
    "拼多多": "{brand}{core}{spec}大容量学生办公{kw}真空便携男女士",
    "小红书": "{brand}{core}｜6小时保温随行杯",
}
FORBIDDEN = ["最好", "第一", "100%", "顶级", "国家级", "永不"]


def demo_data():
    """来自 runs_v2 实跑输入（晨露 316 不锈钢保温杯 CL-BW500 一稿三平台）。"""
    return {
        "product": {"brand": "晨露", "model": "CL-BW500", "core": "316不锈钢保温杯",
                    "spec": "500ml", "kw": "保温杯",
                    "selling_points": ["316L 不锈钢内胆，耐腐蚀易清洁",
                                       "真空镀铜保温层，6 小时水温 ≥ 55℃",
                                       "旋拧密封倒置不漏", "弹跳开盖单手可开"]},
        "source_category": "餐饮具/杯具/保温杯",
        "target_categories": {"抖店": "餐饮具/水杯/保温杯", "拼多多": "家居用品/水杯/保温杯"},
        "platforms": ["淘宝", "抖店", "拼多多"],
    }


def step1_category_map(payload, outdir):
    """S1 类目属性映射：读输入，源类目 → 各平台类目逐条映射。"""
    src = payload.get("source_category") or ""
    targets = payload.get("target_categories") or {}
    if not src or not targets:
        raise SystemExit("[错误] source_category 与 target_categories 均不能为空：缺失让用户补齐")
    leaf = src.split("/")[-1]
    mapping = []
    for platform, tgt in targets.items():
        conf = "高" if leaf and leaf in tgt else "中"
        mapping.append({"platform": platform, "source": src, "target": tgt,
                        "basis": "叶子类目同名命中" if conf == "高" else "语义近似，需人工确认",
                        "confidence": conf})
    result = {"mapping": mapping, "count": len(mapping)}
    path = os.path.join(outdir, "step1_类目映射.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result, path


def step2_title_rewrite(payload, outdir):
    """S2 标题多平台改写：读 S1 产物（沿用其平台清单），按字数上限生成标题。"""
    s1 = json.load(open(os.path.join(outdir, "step1_类目映射.json"), encoding="utf-8"))
    platforms = payload.get("platforms") or [m["platform"] for m in s1["mapping"]]
    p = payload.get("product") or {}
    titles, warnings = [], []
    for plat in platforms:
        limit = PLATFORM_LIMIT.get(plat)
        if limit is None:
            warnings.append(f"{plat}：不在常量表，按 30 字上限处理，发布前查官方")
            limit = 30
        title = TITLE_TEMPLATE.get(plat, "{brand}{core}{spec}{kw}").format(
            brand=p.get("brand", ""), core=p.get("core", ""), spec=p.get("spec", ""),
            kw=p.get("kw", ""))
        over = len(title) - limit
        if over > 0:
            warnings.append(f"{plat}：模板标题 {len(title)} 字超 {limit} 字上限 {over} 字，已截断修饰词")
            title = title[:limit]
        hits = [w for w in FORBIDDEN if w in title]
        if hits:
            warnings.append(f"{plat}：标题命中极限词 {hits}，已拦截，请人工改写")
            continue
        titles.append({"platform": plat, "title": title, "chars": len(title),
                       "limit": limit, "compliance": "未命中极限词"})
    result = {"titles": titles, "warnings": warnings}
    path = os.path.join(outdir, "step2_标题改写.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result, path


def step3_listing_draft(payload, outdir):
    """S3 上架草稿汇总：读 S1+S2 产物，拼装草稿清单。"""
    s1 = json.load(open(os.path.join(outdir, "step1_类目映射.json"), encoding="utf-8"))
    s2 = json.load(open(os.path.join(outdir, "step2_标题改写.json"), encoding="utf-8"))
    cat = {m["platform"]: m["target"] for m in s1["mapping"]}
    p = payload.get("product") or {}
    lines = ["**AI 生成内容**", "", "# 一稿多平台上架草稿", "",
             "| 平台 | 目标类目 | 标题（字数/上限） | 核心卖点 |",
             "|---|---|---|---|"]
    rows = []
    for i, t in enumerate(s2["titles"], 1):
        plat = t["platform"]
        point = (p.get("selling_points") or [""])[0]
        lines.append(f"| {plat} | {cat.get(plat, '（未映射）')} "
                     f"| {t['title']}（{t['chars']}/{t['limit']} 字） | {point} |")
        rows.append({"平台": plat, "目标类目": cat.get(plat, ""),
                     "标题": t["title"], "字数": t["chars"], "上限": t["limit"],
                     "合规": t["compliance"]})
    if s2["warnings"]:
        lines += ["", "## 改写警告", ""] + [f"- {w}" for w in s2["warnings"]]
    md_path = os.path.join(outdir, "上架草稿.md")
    open(md_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    csv_path = os.path.join(outdir, "类目映射表.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["平台", "目标类目", "标题", "字数", "上限", "合规"])
        for r in rows:
            w.writerow([r["平台"], r["目标类目"], r["标题"], r["字数"], r["上限"], r["合规"]])
    return [md_path, csv_path]


def main():
    ap = argparse.ArgumentParser(description="一稿多平台 Listing 生成工作流（映射→标题→草稿）")
    ap.add_argument("--input", help="输入 JSON")
    ap.add_argument("--outdir", default=OUT_DEFAULT)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = demo_data() if a.demo else (
        json.load(open(a.input, encoding="utf-8")) if a.input else ap.error("需要 --input 或 --demo"))
    os.makedirs(a.outdir, exist_ok=True)

    s1, p1 = step1_category_map(payload, a.outdir)
    s2, p2 = step2_title_rewrite(payload, a.outdir)
    files = step3_listing_draft(payload, a.outdir)

    result_path = os.path.join(a.outdir, "flow_result.json")
    json.dump({"flow": "listing-multiplatform-flow", "steps": [p1, p2] + files,
               "summary": f"映射 {s1['count']} 个平台类目，产出 {len(s2['titles'])} 条达标标题",
               "note": "字数与映射由本脚本判定；卖点措辞润色由模型按 prompt.txt 完成"},
              open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"工作流完成 —— 映射 {s1['count']} 个平台，标题 {len(s2['titles'])} 条，"
          f"警告 {len(s2['warnings'])} 条")
    for f in [p1, p2] + files + [result_path]:
        print(" 产物:", f)


if __name__ == "__main__":
    main()
