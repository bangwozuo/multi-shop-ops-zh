# -*- coding: utf-8 -*-
"""
超卖预警 —— 可用库存/在途订单/安全水位三口径确定性判定 + 产物生成。

职责边界（重要）：
  本脚本只做**确定性计算与产物生成**：净可用库存、水位偏离、两级判定（紧急/高）、
  CSV/JSON/MD 落盘。补货紧迫度措辞、调拨建议，由模型按 prompt.txt 完成。

判定规则（与 prompt.txt 一致，可用 rules 覆盖）：
  R1 净可用 = 可用库存 - 在途订单 < 0        → 「超卖风险」，级别 紧急
  R2 净可用 ≥ 0 且 可用库存 < 安全水位线      → 「低库存预警」，级别 高
  R3 其余                                     → 正常，进「未命中项」
  R4 偏离 = 可用库存 - 安全水位线（件）
  数据缺失的 SKU 不估算，直接进「需人工确认」。

用法：
  python alert_scan.py --input input.json --outdir out
  python alert_scan.py --demo --outdir out

产物：
  out/预警清单.csv      逐条判定（指标/当前值/基线/偏离/级别/判定规则）
  out/超卖预警报告.md   人类可读报告（预警清单 + 未命中项 + 需人工确认）
  out/alerts.json       机器可读结果（供工作流/下游技能读取）
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DEFAULT = os.path.normpath(os.path.join(os.path.dirname(HERE), "out"))

DEFAULT_RULES = {
    "oversell_rule": "可用库存 - 在途订单 < 0 判超卖（紧急）",
    "low_rule": "可用库存 < 安全水位线判低库存（高）",
}


def demo_data():
    """来自 runs_v2 实跑输入（三店共享仓 5 个 SKU 快照 + 安全水位线）。"""
    return {
        "metrics": [
            {"sku": "SKU-1001 316不锈钢保温杯500ml", "available": 45, "in_transit_orders": 60},
            {"sku": "SKU-1002 玻璃双层水杯450ml", "available": 120, "in_transit_orders": 30},
            {"sku": "SKU-1003 陶瓷马克杯380ml", "available": 18, "in_transit_orders": 15},
            {"sku": "SKU-1004 便携榨汁杯400ml", "available": 0, "in_transit_orders": 5},
            {"sku": "SKU-1005 家用烘鞋器", "available": 210, "in_transit_orders": 12},
        ],
        "baseline": {
            "SKU-1001": 50, "SKU-1002": 50, "SKU-1003": 30, "SKU-1004": 20, "SKU-1005": 50,
        },
        "rules": {},
    }


def _parse_sku(s: str) -> str:
    return s.split()[0] if s.split() else s


def scan(payload):
    rules = {**DEFAULT_RULES, **(payload.get("rules") or {})}
    baseline = payload.get("baseline") or {}
    rows = payload.get("metrics") or []
    if not rows:
        raise SystemExit("[错误] metrics 为空：请提供可用库存与在途订单快照，缺失清单让用户补齐，不估算")

    alerts, no_alert, need_confirm = [], [], []
    for r in rows:
        sku = _parse_sku(r["sku"])
        name = r["sku"]
        if "available" not in r or "in_transit_orders" not in r:
            need_confirm.append(f"{name}：缺少可用库存或在途订单字段，不估算，请补齐后重扫")
            continue
        avail, transit = int(r["available"]), int(r["in_transit_orders"])
        net = avail - transit
        water = baseline.get(sku)
        if water is None:
            need_confirm.append(f"{name}：无安全水位线基线，无法判低库存，请补充水位配置")
            continue

        if net < 0:
            alerts.append({
                "#": str(len(alerts) + 1), "指标": f"{name} 净可用库存",
                "当前值": f"{avail} 件（在途订单 {transit} 件）",
                "基线": f"安全水位 {water} 件",
                "偏离": f"{net} 件（净可用）；{avail - water} 件（对水位）",
                "级别": "紧急", "判定规则": "可用库存 - 在途订单 < 0 判超卖", "类型": "超卖风险"})
        elif avail < water:
            alerts.append({
                "#": str(len(alerts) + 1), "指标": f"{name} 可用库存",
                "当前值": f"{avail} 件（在途订单 {transit} 件）",
                "基线": f"安全水位 {water} 件",
                "偏离": f"{avail - water} 件", "级别": "高",
                "判定规则": "可用库存 < 安全水位线判低库存", "类型": "低库存预警"})
        else:
            no_alert.append(f"{name}：可用 {avail} 件、净可用 {net} 件、水位 {water} 件 —— 正常")

    stats = {
        "扫描 SKU 数": len(rows), "预警条数": len(alerts),
        "紧急": len([a for a in alerts if a["级别"] == "紧急"]),
        "高": len([a for a in alerts if a["级别"] == "高"]),
        "正常条数": len(no_alert), "需人工确认条数": len(need_confirm),
    }
    return alerts, no_alert, need_confirm, stats


def write_outputs(alerts, no_alert, need_confirm, stats, outdir):
    os.makedirs(outdir, exist_ok=True)
    files = []

    csv_path = os.path.join(outdir, "预警清单.csv")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["#", "指标", "当前值", "基线", "偏离", "级别", "判定规则", "类型"])
        w.writeheader()
        for r in alerts:
            w.writerow(r)
    files.append(csv_path)

    md = ["**AI 生成内容**", "", "## 预警清单", "",
          "| # | 指标 | 当前值 | 基线 | 偏离 | 级别 | 判定规则 |",
          "|---|---|---|---|---|---|---|"]
    for r in alerts:
        md.append(f"| {r['#']} | {r['指标']} | {r['当前值']} | {r['基线']} | {r['偏离']} | {r['级别']} | {r['判定规则']} |")
    md += ["", "## 未命中项", ""] + [f"{i}. {x}" for i, x in enumerate(no_alert, 1)]
    md += ["", "## 需人工确认", ""] + [f"{i}. {x}" for i, x in enumerate(need_confirm, 1)]
    md_path = os.path.join(outdir, "超卖预警报告.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    files.append(md_path)

    js_path = os.path.join(outdir, "alerts.json")
    with open(js_path, "w", encoding="utf-8") as f:
        json.dump({"stats": stats, "alerts": alerts, "no_alert": no_alert,
                   "need_confirm": need_confirm,
                   "note": "超卖与低库存判定由本脚本完成；补货紧迫度与调拨建议由模型按 prompt.txt 完成"},
                  f, ensure_ascii=False, indent=2)
    files.append(js_path)
    return files


def main():
    ap = argparse.ArgumentParser(description="超卖预警（净可用 + 安全水位两级判定）")
    ap.add_argument("--input", help="输入 JSON（metrics/baseline/rules）")
    ap.add_argument("--outdir", default=OUT_DEFAULT)
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = demo_data() if a.demo else (
        json.load(open(a.input, encoding="utf-8")) if a.input else ap.error("需要 --input 或 --demo"))

    alerts, no_alert, need_confirm, stats = scan(payload)
    files = write_outputs(alerts, no_alert, need_confirm, stats, a.outdir)
    print(f"扫描完成 —— {stats['扫描 SKU 数']} 个 SKU：预警 {stats['预警条数']} 条"
          f"（紧急 {stats['紧急']} / 高 {stats['高']}），需人工确认 {stats['需人工确认条数']} 条")
    for f in files:
        print(" 产物:", f, f"({os.path.getsize(f) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
