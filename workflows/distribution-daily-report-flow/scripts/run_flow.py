# -*- coding: utf-8 -*-
"""
铺货日报生成工作流 —— 端到端编排脚本（与 SKILL.md 的 DAG 一致）。

流程：
  S1 铺货盘点     三店在售 SKU 覆盖统计与缺口清单（铺货率 = 各店在售 ÷ 主店 SKU 总数）
  S2 库存判定     净可用 = 可用 - 在途订单 < 0 → 超卖；可用 < 安全水位 → 低库存
  S3 价格对比     本店售价 vs 竞品价，差价率 =（本店 - 竞品）÷ 竞品 × 100%
  S4 日报汇总     三段拼装成当日铺货日报（带 AI 标识 + 人工确认位）

本脚本承担 S1-S4 的确定性部分；日报结论措辞与跟价建议由模型按 prompt.txt 完成。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物：
  out/step1_铺货盘点.json / out/step2_库存判定.json / out/step3_价格对比.json
  out/日报数据.csv / out/铺货日报.md    最终交付物
  out/flow_result.json                  机器可读汇总
"""
from __future__ import annotations

import argparse
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(HERE), "out"))


def demo_data():
    """来自 runs_v2 实跑输入（2026-10-08 铺货日报定时任务，数据日期 2026-10-07）。"""
    return {
        "data_date": "2026-10-07",
        "shops": ["晨露家居淘宝店", "晨露家居抖店店", "晨露家居拼多多店"],
        "listing": {"total_sku": 47,
                    "per_shop": {"晨露家居淘宝店": 47, "晨露家居抖店店": 45,
                                 "晨露家居拼多多店": 42},
                    "missing": {"晨露家居抖店店": ["SKU-1004 便携榨汁杯"],
                                "晨露家居拼多多店": ["SKU-1003 陶瓷马克杯", "SKU-1004 便携榨汁杯",
                                                    "SKU-1007 挂烫机蒸汽喷头"]}},
        "stock": [
            {"sku": "SKU-1001 316不锈钢保温杯", "available": 45, "in_transit_orders": 60, "water": 50},
            {"sku": "SKU-1002 玻璃双层水杯", "available": 120, "in_transit_orders": 30, "water": 50},
            {"sku": "SKU-1003 陶瓷马克杯", "available": 18, "in_transit_orders": 15, "water": 30},
            {"sku": "SKU-1004 便携榨汁杯", "available": 0, "in_transit_orders": 5, "water": 20},
            {"sku": "SKU-1005 家用烘鞋器", "available": 210, "in_transit_orders": 12, "water": 50},
        ],
        "price": [
            {"sku": "SKU-1001 316不锈钢保温杯", "our": 89.0, "comp": 69.9},
            {"sku": "SKU-1002 玻璃双层水杯", "our": 39.9, "comp": 35.0},
            {"sku": "SKU-1003 陶瓷马克杯", "our": 29.9, "comp": 25.9},
        ],
    }


def step1_listing_audit(payload, outdir):
    """S1 铺货盘点：读输入，算各店铺货率与缺口。"""
    lst = payload.get("listing") or {}
    total = lst.get("total_sku") or 0
    if not total:
        raise SystemExit("[错误] listing.total_sku 缺失：请提供主店在售 SKU 总数，不估算")
    rows = []
    for shop, cnt in (lst.get("per_shop") or {}).items():
        rate = cnt / total * 100
        rows.append({"shop": shop, "listed": cnt, "total": total,
                     "rate": round(rate, 1), "missing": lst.get("missing", {}).get(shop, [])})
    result = {"rows": rows}
    path = os.path.join(outdir, "step1_铺货盘点.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result, path


def step2_stock_check(payload, outdir):
    """S2 库存判定：读输入，净可用口径两级判定。"""
    alerts = []
    for r in payload.get("stock") or []:
        avail, transit = int(r["available"]), int(r["in_transit_orders"])
        net = avail - transit
        w = r.get("water")
        if net < 0:
            alerts.append({"sku": r["sku"], "level": "紧急", "type": "超卖风险", "net": net,
                           "avail": avail, "water": w})
        elif w is not None and avail < w:
            alerts.append({"sku": r["sku"], "level": "高", "type": "低库存预警", "net": net,
                           "avail": avail, "water": w})
    result = {"alert_count": len(alerts), "alerts": alerts}
    path = os.path.join(outdir, "step2_库存判定.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result, path


def step3_price_compare(payload, outdir):
    """S3 价格对比：读输入，算差价率。"""
    rows = []
    for r in payload.get("price") or []:
        diff = (r["our"] - r["comp"]) / r["comp"] * 100
        tag = "高于竞品" if diff > 0 else "低于竞品"
        rows.append({"sku": r["sku"], "our": r["our"], "comp": r["comp"],
                     "diff": round(diff, 1), "tag": tag})
    result = {"rows": rows}
    path = os.path.join(outdir, "step3_价格对比.json")
    json.dump(result, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return result, path


def step4_report(payload, outdir):
    """S4 日报汇总：读前三步产物，拼装日报。"""
    s1 = json.load(open(os.path.join(outdir, "step1_铺货盘点.json"), encoding="utf-8"))["rows"]
    s2 = json.load(open(os.path.join(outdir, "step2_库存判定.json"), encoding="utf-8"))["alerts"]
    s3 = json.load(open(os.path.join(outdir, "step3_价格对比.json"), encoding="utf-8"))["rows"]
    date = payload.get("data_date", "")

    lines = ["**AI 生成内容**", "", f"# 铺货日报（数据日期 {date}）", "",
             "## 一、铺货盘点", "",
             "| 店铺 | 在售 SKU | 主店总数 | 铺货率 | 缺口 |",
             "|---|---|---|---|---|"]
    for r in s1:
        miss = "、".join(r["missing"]) if r["missing"] else "—"
        lines.append(f"| {r['shop']} | {r['listed']} | {r['total']} | {r['rate']}% | {miss} |")

    lines += ["", "## 二、库存预警", "",
              "| SKU | 级别 | 类型 | 可用 | 在途订单 | 净可用 | 水位 |", "|---|---|---|---|---|---|---|"]
    for a in s2:
        lines.append(f"| {a['sku']} | {a['level']} | {a['type']} | {a['avail']} 件 "
                     f"| {a['avail'] - a['net']} 件 | {a['net']} 件 | {a['water']} 件 |")

    lines += ["", "## 三、价格对比", "",
              "| SKU | 本店价 | 竞品价 | 差价率 | 结论 |", "|---|---|---|---|---|"]
    for r in s3:
        lines.append(f"| {r['sku']} | {r['our']} 元 | {r['comp']} 元 "
                     f"| {r['diff']:+.1f}% | {r['tag']} |")
    lines += ["", "---", "", "*本日报由工作流脚本自动汇总，结论与跟价建议须经运营人工确认后发布*", ""]

    md_path = os.path.join(outdir, "铺货日报.md")
    open(md_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")

    csv_path = os.path.join(outdir, "日报数据.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["板块", "对象", "数值", "级别/差价率", "说明"])
        for r in s1:
            w.writerow(["铺货盘点", r["shop"], f"{r['listed']}/{r['total']}",
                        f"{r['rate']}%", "缺口: " + ("、".join(r["missing"]) or "无")])
        for a in s2:
            w.writerow(["库存预警", a["sku"], f"{a['avail']}件", a["level"], a["type"]])
        for r in s3:
            w.writerow(["价格对比", r["sku"], f"{r['our']}元", f"{r['diff']:+.1f}%", r["tag"]])
    return [md_path, csv_path]


def main():
    ap = argparse.ArgumentParser(description="铺货日报生成工作流（盘点→库存→价格→日报）")
    ap.add_argument("--input", help="输入 JSON")
    ap.add_argument("--outdir", default=OUT_DEFAULT)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = demo_data() if a.demo else (
        json.load(open(a.input, encoding="utf-8")) if a.input else ap.error("需要 --input 或 --demo"))
    os.makedirs(a.outdir, exist_ok=True)

    s1, p1 = step1_listing_audit(payload, a.outdir)
    s2, p2 = step2_stock_check(payload, a.outdir)
    s3, p3 = step3_price_compare(payload, a.outdir)
    files = step4_report(payload, a.outdir)

    result_path = os.path.join(a.outdir, "flow_result.json")
    json.dump({"flow": "distribution-daily-report-flow", "steps": [p1, p2, p3] + files,
               "summary": f"铺货 {len(s1['rows'])} 店、库存预警 {s2['alert_count']} 条、"
                          f"价格对比 {len(s3['rows'])} 个 SKU，日报已生成",
               "note": "数值由本脚本汇总；日报结论措辞由模型按 prompt.txt 完成"},
              open(result_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"工作流完成 —— 铺货 {len(s1['rows'])} 店、预警 {s2['alert_count']} 条、"
          f"比价 {len(s3['rows'])} 个 SKU")
    for f in [p1, p2, p3] + files + [result_path]:
        print(" 产物:", f)


if __name__ == "__main__":
    main()
